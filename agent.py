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

def detect_platforms(data):
    platforms = ["PC"]
    platforms_raw = data.get("platforms", {})
    if platforms_raw.get("windows") or platforms_raw.get("mac") or platforms_raw.get("linux"):
        if "PC" not in platforms:
            platforms.append("PC")

    categories = [c.get("description", "").lower() for c in data.get("categories", [])]
    controller = data.get("controller_support", "none")
    
    if controller == "full" or any("controller" in c for c in categories):
        platforms.extend(["PlayStation", "Xbox", "Nintendo Switch"])
    else:
        platforms.extend(["PlayStation", "Xbox"])
        
    return list(dict.fromkeys(platforms))

def get_detailed_price_en(app_id):
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=english"
    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}
    try:
        res = requests.get(url, headers=headers, timeout=8).json()
        if not res:
            return None
        first_key = next(iter(res))
        entry = res[first_key]
        if entry.get("success"):
            data = entry["data"]
            po = data.get("price_overview")
            if po:
                return {
                    "title": data.get("name"),
                    "discount_pct": po.get("discount_percent", 0),
                    "final_price": clean_currency(po.get("final_formatted", "")),
                    "initial_price": clean_currency(po.get("initial_formatted", ""))
                }
    except Exception as e:
        print(f"Error fetching price for {app_id}: {e}")
    return None

def get_full_game_payload(app_id, action_type):
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=english"
    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}
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
        header_image = data.get("header_image", "")

        preview_video = ""
        movies = data.get("movies", [])
        if movies:
            first_movie = movies[0]
            mp4_dict = first_movie.get("mp4", {})
            webm_dict = first_movie.get("webm", {})
            raw_url = mp4_dict.get("max") or mp4_dict.get("480") or webm_dict.get("max") or ""
            if raw_url:
                preview_video = raw_url.replace("http://", "https://")

        po = data.get("price_overview", {})
        price = clean_currency(po.get("final_formatted", "Free"))
        original_price = clean_currency(po.get("initial_formatted", price))
        discount = po.get("discount_percent", 0)

        controller_support = data.get("controller_support", "none")
        raw_categories = [c.get("description", "") for c in data.get("categories", [])]

        raw_desc = data.get("detailed_description", "")
        clean_desc = clean_html_description(raw_desc)
        short_desc = clean_html_description(data.get("short_description", ""))

        max_players = "2-4"
        desc_lower = (clean_desc + " " + short_desc).lower()
        if any(w in desc_lower for w in ["8 player", "8-player", "up to 8"]):
            max_players = "2-8"
        elif any(w in desc_lower for w in ["6 player", "6-player", "up to 6"]):
            max_players = "2-6"
        elif any(w in desc_lower for w in ["2 player only", "two players", "co-op only", "pair"]):
            max_players = "2"

        g2a_info = get_g2a_deal(title)

        status_mapping = {
            "approve_tested": "TESTED_COUCH_PROOF",
            "approve_untested": "LISTED_DEAL",
            "bundle": "BUNDLE_CANDIDATE"
        }

        platforms = detect_platforms(data)

        return {
            "id": str(app_id),
            "title": title,
            "banner": header_image,
            "preview_video": preview_video,
            "players": f"{max_players} Players",
            "price": price,
            "original_price": original_price,
            "discount_pct": discount,
            "controller_ready": controller_support in ["full", "partial"],
            "controller_type": "Full Controller Support" if controller_support == "full" else "Partial / Keyboard",
            "store_url": f"https://store.steampowered.com/app/{app_id}/",
            "g2a_url": g2a_info["url"],
            "status": status_mapping.get(action_type, "LISTED_DEAL"),
            "categories": [c for c in raw_categories if any(k.lower() in c.lower() for k in ["co-op", "shared", "split", "multi-player"])],
            "description": clean_desc,
            "short_description": short_desc,
            "platforms": platforms
        }
    except Exception as e:
        print(f"Error building payload for {app_id}: {e}")
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

def fetch_steam_couch_deals(min_discount=20, max_results=15):
    query_url = (
        "https://store.steampowered.com/search/results/"
        "?query=&start=0&count=50&dynamic_data=&sort_by=_ASC"
        "&category2=24%2C39"
        "&specials=1"
        "&cc=us&l=english&json=1"
    )
    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}
    deals = []
    try:
        r = requests.get(query_url, headers=headers, timeout=10).json()
        for item in r.get("items", []):
            match = re.search(r"/apps/(\d+)/", item.get("logo", ""))
            if not match:
                continue
            app_id = match.group(1)
            details = get_detailed_price_en(app_id)
            if not details:
                continue
            if details["discount_pct"] >= min_discount:
                deals.append({
                    "app_id": app_id,
                    "title": details["title"],
                    "discount_pct": details["discount_pct"],
                    "final_price": details["final_price"],
                    "initial_price": details["initial_price"],
                    "url": f"https://store.steampowered.com/app/{app_id}/"
                })
            if len(deals) >= max_results:
                break
    except Exception as e:
        print(f"Fetch error: {e}")
    return deals

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, app_id = query.data.split(":")

    approved_list = load_data(APPROVED_FILE, [])

    if action in ["approve_tested", "approve_untested", "bundle"]:
        entry = {"app_id": app_id, "status": action}
        if entry not in approved_list:
            approved_list.append(entry)
            save_data(APPROVED_FILE, approved_list)

        print(f"\n[ACTION] Processing {action} for AppID {app_id}...")
        payload = get_full_game_payload(app_id, action)
        cloud_synced = False
        if payload:
            cloud_synced = push_to_supabase(payload)

        await query.edit_message_reply_markup(reply_markup=None)
        if cloud_synced:
            badge_msg = "🛋 Verified Couch-Proof" if action == "approve_tested" else "🌐 Standard Verified Deal"
            await query.message.reply_text(f"✅ *{payload['title']}* published live on Supabase ({badge_msg})!", parse_mode="Markdown")
        else:
            await query.message.reply_text("✅ Saved locally. (Temporary cloud connection issue)")

    elif action == "reject":
        print(f"\n[ACTION] ❌ Rejected AppID {app_id}")
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("❌ *Deal rejected.*")

async def run_scan_cycle(bot):
    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 🔍 Starting scheduled couch deals scan...")
    history = set(load_data(HISTORY_FILE, []))
    deals = fetch_steam_couch_deals(min_discount=20, max_results=10)

    count = 0
    for deal in deals:
        app_id = deal["app_id"]
        if app_id in history:
            continue

        g2a_info = get_g2a_deal(deal["title"])

        keyboard = [
            [
                InlineKeyboardButton("🛋️ Approve (Couch-Proof)", callback_data=f"approve_tested:{app_id}"),
                InlineKeyboardButton("🌐 Publish (No Badge)", callback_data=f"approve_untested:{app_id}")
            ],
            [
                InlineKeyboardButton("📦 Add to Bundle", callback_data=f"bundle:{app_id}"),
                InlineKeyboardButton("❌ Discard", callback_data=f"reject:{app_id}")
            ],
            [
                InlineKeyboardButton("🏷️ G2A Key Deal", url=g2a_info["url"]),
                InlineKeyboardButton("🛒 Steam Page", url=deal["url"])
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        text = (
            f"🎮 *NEW COUCH CO-OP DEAL FOUND!*\n\n"
            f"🕹 *Title:* {deal['title']}\n"
            f"👥 *Multiplayer:* Shared/Split Screen\n"
            f"💥 *Discount:* -{deal['discount_pct']}% at *{deal['final_price']}* (was {deal['initial_price']})\n\n"
            f"Choose publication status:"
        )

        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        history.add(app_id)
        count += 1
        await asyncio.sleep(1)

    save_data(HISTORY_FILE, list(history))
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ✅ Scan complete: {count} new deals sent to Telegram.")

async def schedule_worker(app):
    await run_scan_cycle(app.bot)
    while True:
        delay_seconds = random.randint(12600, 16200)
        print(f"⏱ Next scan scheduled in ~{round(delay_seconds/3600, 1)} hours.")
        await asyncio.sleep(delay_seconds)
        await run_scan_cycle(app.bot)

async def on_startup(app):
    asyncio.create_task(schedule_worker(app))
    print("👂 Bot listening and Supabase sync ready.")

def main():
    print("Starting Couch Agent Complete (4 Time Slots + G2A + Supabase)...")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(CallbackQueryHandler(handle_button))
    app.run_polling()

if __name__ == "__main__":
    main()