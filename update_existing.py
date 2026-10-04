import json
import requests
from agent import get_full_game_payload, push_to_supabase

with open("approved_games.json", "r", encoding="utf-8") as f:
    games = json.load(f)

print(f"Aggiornamento di {len(games)} giochi esistenti con descrizioni e piattaforme...")
for item in games:
    app_id = item["app_id"]
    payload = get_full_game_payload(app_id, "approve_tested")
    if payload:
        if push_to_supabase(payload):
            print(f"  [OK] {payload['title']} aggiornato con descrizione completa e piattaforme!")
        else:
            print(f"  [ERRORE] Impossibile aggiornare {payload['title']}")

print("\nDatabase Supabase allineato!")