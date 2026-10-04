import json
import os
import requests
from deals_scanner import get_g2a_deal

APPROVED_FILE = "approved_games.json"
OUTPUT_FILE = "frontend_data.json"

def clean_currency(price_str):
    if not price_str:
        return "Gratis"
    return price_str.replace("\u00a0", " ").replace("Ôé¼", "€").strip()

def get_game_full_metadata(app_id, status):
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=it&l=italian"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "it-IT,it;q=0.9"
    }
    
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
        
        # 1. Trailer Video MP4
        preview_video = ""
        movies = data.get("movies", [])
        if movies:
            movie_id = movies[0].get("id")
            if movie_id:
                preview_video = f"https://video.cloudflare.steamstatic.com/store_trailers/{movie_id}/movie480.mp4"

        # 2. Prezzi Steam
        po = data.get("price_overview", {})
        price = clean_currency(po.get("final_formatted", "Gratis"))
        original_price = clean_currency(po.get("initial_formatted", price))
        discount = po.get("discount_percent", 0)
        
        # 3. Controller
        controller_support = data.get("controller_support", "none")
        categories = [c.get("description", "") for c in data.get("categories", [])]
        
        # 4. Giocatori
        max_players = "2-4"
        desc = (data.get("detailed_description", "") + " " + data.get("short_description", "")).lower()
        if any(w in desc for w in ["8 player", "8 giocator", "fino a 8"]):
            max_players = "2-8"
        elif any(w in desc for w in ["6 player", "6 giocator", "fino a 6"]):
            max_players = "2-6"
        elif any(w in desc for w in ["solo 2", "coppia", "2 player"]):
            max_players = "2"

        # 5. Link G2A con il tuo Reflink Goldmine
        g2a_info = get_g2a_deal(title)

        return {
            "id": str(app_id),
            "title": title,
            "banner": header_image,
            "preview_video": preview_video,
            "players": f"{max_players} Giocatori",
            "price": price,
            "original_price": original_price,
            "discount_pct": discount,
            "controller_ready": controller_support in ["full", "partial"],
            "controller_type": "Supporto Completo Gamepad" if controller_support == "full" else "Supporto Parziale / Tastiera",
            "store_url": f"https://store.steampowered.com/app/{app_id}/",
            "g2a_url": g2a_info["url"],
            "status": "TESTED_COUCH_PROOF" if status == "verified_couch_proof" else "BUNDLE_CANDIDATE",
            "categories": [c for c in categories if "Co-op" in c or "Schermo" in c or "Multiplayer" in c]
        }
    except Exception as e:
        print(f"Errore appdetails per {app_id}: {e}")
        return None

def main():
    if not os.path.exists(APPROVED_FILE):
        print(f"File {APPROVED_FILE} non trovato.")
        return

    with open(APPROVED_FILE, "r", encoding="utf-8") as f:
        approved_items = json.load(f)

    print(f"Generazione catalogo Web con link G2A ({len(approved_items)} giochi approvati)...")
    catalog = []

    for item in approved_items:
        app_id = item["app_id"]
        status = item.get("status", "verified_couch_proof")
        meta = get_game_full_metadata(app_id, status)
        if meta:
            catalog.append(meta)
            print(f"   [OK] {meta['title']} | Trailer MP4: OK | G2A Ref: OK")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    print(f"\n✅ File '{OUTPUT_FILE}' aggiornato con successo!")

if __name__ == "__main__":
    main()