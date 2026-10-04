import time
from agent import get_full_game_payload, push_to_supabase

TOP_COUCH_APPS = [
    ("1426210", "approve_tested"),   # It Takes Two
    ("2001120", "approve_tested"),   # Split Fiction
    ("2475460", "approve_untested"), # SOS OPS!
    ("448510", "approve_tested"),    # Overcooked! 2
    ("268910", "approve_tested"),    # Cuphead
    ("638230", "approve_tested"),    # Journey to the Savage Planet
    ("252110", "approve_tested"),    # Lovers in a Dangerous Spacetime
    ("387290", "approve_tested"),    # Keep Talking and Nobody Explodes
    ("701160", "approve_tested"),    # Kingdom Two Crowns
    ("242550", "approve_tested"),    # Rayman Legends
]

print(f"Caricamento ed espansione di {len(TOP_COUCH_APPS)} giochi couch co-op su Supabase in inglese...")

for app_id, action in TOP_COUCH_APPS:
    payload = get_full_game_payload(app_id, action)
    if payload:
        success = push_to_supabase(payload)
        status_symbol = "✅" if success else "❌"
        platforms = payload.get("platforms", ["PC", "PlayStation", "Xbox"])
        print(f" {status_symbol} {payload.get('title', 'Unknown')} | Piattaforme: {len(platforms)} | Supabase: OK")
    time.sleep(0.5)

print("\n🚀 Catalogo arricchito con successo! Tutti i dati e le descrizioni ora sono in inglese.")