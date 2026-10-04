import asyncio
import datetime
import json
import os
import random
import re
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SUPABASE_URL, SUPABASE_KEY
from deals_scanner import get_g2a_deal

HISTORY_FILE = "notified_deals.json"
APPROVED_FILE = "approved_games.json"

def load_data(filename, default_val):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default_val
    return default_val

def save_data(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def clean_currency(price_str):
    if not price_str:
        return "Free"
    return price_str.replace("\u00a0", " ").replace("Ôé¼", "€").strip()

def clean_html_description(raw_html):
    if not raw_html:
        return ""
    cleaned = re.sub(r'<style.*?</style>', '', raw_html, flags=re.DOTALL)
    cleaned = re.sub(r'<script.*?</script>', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'<br\s*/?>', '\n', cleaned)
    cleaned = re.sub(r'</p>', '\n\n', cleaned)
    cleaned = re.sub(r'</li>', '\n', cleaned)
    cleaned = re.sub(r'<[^>]+>', '', cleaned)
    cleaned = re.sub(r'\n\s*\n+', '\n\n', cleaned)
    return cleaned.strip()

def detect_player_count(desc_text, short_text):
    full_text = (desc_text + " " + short_text).lower()
    if any(w in full_text for w in ["8 players", "8-player", "up to 8", "8 friends", "8 concurrent"]):
        return "8 Players (A Lot! 🛋️🎉)"
    elif any(w in full_text for w in ["6 players", "6-player", "up to 6"]):
        return "6 Players"
    elif any(w in full_text for w in ["4 players", "4-player", "up to 4", "four players"]):
        return "4 Players"
    elif any(w in full_text for w in ["3 players", "3-player", "up to 3"]):
        return "3 Players"
    elif any(w in full_text for w in ["2 players only", "two players", "co-op only", "pair"]):
        return "2 Players Only"
    return "2-4 Players"

def get_full_game_payload(app_id, action_type):
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=english"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        if not res:
            return None
        first_key = next(iter(res))
        entry = res[first_key]
        if not entry.get("success"):
            return None
        data = entry["data"]
        title = data.get("name", "Unknown Game")
        banner = data.get("header_image", "")

        # Screenshot per carosello
        raw_shots = data.get("screenshots", [])
        screenshots = [s.get("path_full") for s in raw_shots[:4] if s.get("path_full")]

        po = data.get("price_overview", {})
        price = clean_currency(po.get("final_formatted", "Free"))
        orig_price = clean_currency(po.get("initial_formatted", price))
        discount = po.get("discount_percent", 0)

        controller_support = data.get("controller_support", "none")
        desc = clean_html_description(data.get("detailed_description", ""))
        short_desc = clean_html_description(data.get("short_description", ""))
        players = detect_player_count(desc, short_desc)

        platforms = ["PC", "Steam"]
        if controller_support == "full":
            platforms.extend(["PlayStation", "Xbox", "Nintendo Switch", "Game Pass", "GeForce NOW"])

        status_map = {
            "approve_tested": "TESTED_COUCH_PROOF",
            "approve_untested": "LISTED_DEAL",
            "bundle": "BUNDLE_CANDIDATE"
        }

        g2a_info = get_g2a_deal(title)

        return {
            "id": str(app_id),
            "title": title,
            "banner": banner,
            "screenshots": screenshots,
            "players": players,
            "price": price,
            "original_price": orig_price,
            "discount_pct": discount,
            "controller_ready": controller_support in ["full", "partial"],
            "store_url": f"https://store.steampowered.com/app/{app_id}/",
            "g2a_url": g2a_info["url"],
            "status": status_map.get(action_type, "LISTED_DEAL"),
            "description": desc,
            "short_description": short_desc,
            "platforms": list(dict.fromkeys(platforms))
        }
    except Exception as e:
        print(f"Error fetching {app_id}: {e}")
        return None

def push_to_supabase(payload):
    endpoint = f"{SUPABASE_URL}/rest/v1/couch_games"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }
    try:
        r = requests.post(endpoint, headers=headers, json=[payload], timeout=12)
        return r.status_code in [200, 201]
    except Exception as e:
        print(f"Supabase push error: {e}")
        return False

def fetch_all_couch_deals():
    url = (
        "https://store.steampowered.com/search/results/"
        "?query=&start=0&count=50&dynamic_data=&sort_by=_ASC"
        "&category2=24%2C39"
        "&specials=1"
        "&cc=us&l=english&json=1"
    )
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10).json()
        return r.get("items", [])
    except Exception as e:
        print(f"Fetch error: {e}")
        return []

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, app_id = query.data.split(":")

    if action in ["approve_tested", "approve_untested"]:
        payload = get_full_game_payload(app_id, action)
        if payload:
            push_to_supabase(payload)
            badge_name = "🛋️ Couch-Proof (Verified)" if action == "approve_tested" else "🌐 Untested (Community Notice)"
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(f"✅ *{payload['title']}* aggiunto a catalogo come *{badge_name}* ({payload['players']})!", parse_mode="Markdown")
    elif action == "reject":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("❌ *Gioco scartato.*")

async def run_scan_cycle(bot):
    history = set(load_data(HISTORY_FILE, []))
    items = fetch_all_couch_deals()

    for item in items:
        match = re.search(r"/apps/(\d+)/", item.get("logo", ""))
        if not match:
            continue
        app_id = match.group(1)
        if app_id in history:
            continue

        payload = get_full_game_payload(app_id, "approve_untested")
        if not payload:
            continue

        # Inserisci nel catalogo come untested finché non decidi tu
        push_to_supabase(payload)

        # Invia la scheda a Telegram con dettagli precisi sul numero di giocatori
        keyboard = [
            [
                InlineKeyboardButton(f"🛋️ Conferma Couch-Proof ({payload['players']})", callback_data=f"approve_tested:{app_id}"),
                InlineKeyboardButton("🌐 Lascia Untested", callback_data=f"approve_untested:{app_id}")
            ],
            [
                InlineKeyboardButton("❌ Rimuovi dal Catalogo", callback_data=f"reject:{app_id}"),
                InlineKeyboardButton("🛒 Steam Page", url=payload["store_url"])
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        msg_text = (
            f"🎮 *NUOVO TITOLO COUCH CO-OP RILEVATO!*\n\n"
            f"🕹 *Titolo:* {payload['title']}\n"
            f"👥 *Giocatori Rilevati:* {payload['players']}\n"
            f"💥 *Prezzo:* {payload['price']} (-{payload['discount_pct']}%)\n\n"
            f"È già visibile sul sito con avviso di test. Vuoi certificarlo Couch-Proof?"
        )

        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg_text, parse_mode="Markdown", reply_markup=reply_markup)
        history.add(app_id)
        await asyncio.sleep(1)

    save_data(HISTORY_FILE, list(history))

async def on_startup(app):
    asyncio.create_task(run_scan_cycle(app.bot))
    print("Agent in ascolto e scansione Telegram pronta.")

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(CallbackQueryHandler(handle_button))
    app.run_polling()

if __name__ == "__main__":
    main()