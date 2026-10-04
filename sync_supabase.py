import json
import os
import requests
from config import SUPABASE_URL, SUPABASE_KEY

DATA_FILE = "frontend_data.json"

def sync_to_supabase():
    if not os.path.exists(DATA_FILE):
        print(f"File {DATA_FILE} non trovato. Esegui prima 'python export_catalog.py'!")
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        games = json.load(f)

    print(f"Caricamento di {len(games)} giochi approvati su Supabase...")

    # Endpoint REST nativo di Supabase per inserimento/aggiornamento (upsert)
    endpoint = f"{SUPABASE_URL}/rest/v1/couch_games"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"  # Se esiste già, aggiorna i dati senza errori
    }

    try:
        response = requests.post(endpoint, headers=headers, json=games, timeout=15)
        if response.status_code in [200, 201]:
            print("\n✅ SINCRONIZZAZIONE COMPLETATA CON SUCCESSO!")
            print(f"-> {len(games)} giochi ora sono attivi e visibili nel tuo database cloud.")
        else:
            print(f"\n❌ Errore sincronizzazione: HTTP {response.status_code}")
            print(f"Risposta server: {response.text}")
    except Exception as e:
        print(f"\n❌ Errore durante la richiesta: {e}")

if __name__ == "__main__":
    sync_to_supabase()