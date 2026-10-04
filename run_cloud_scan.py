import os
import requests
import json
import re

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

G2A_REF_ID = "reflink-07f53ba10b"

def get_g2a_deal(game_title):
    query = requests.utils.quote(game_title)
    return f"https://www.g2a.com/search?query={query}&ref={G2A_REF_ID}"

def get_couch_deals():
    url = (
        "https://store.steampowered.com/search/results/"
        "?query=&start=0&count=40&dynamic_data=&sort_by=_ASC"
        "&category2=24%2C39"
        "&specials=1"
        "&cc=us&l=english&json=1"
    )
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10).json()
        return r.get("items", [])
    except Exception as e:
        print(f"Error fetching Steam: {e}")
        return []

def main():
    print("Avvio scansione autonoma cloud...")
    items = get_couch_deals()
    print(f"Trovati {len(items)} giochi in saldo con co-op locale.")

if __name__ == "__main__":
    main()