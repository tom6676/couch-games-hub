import requests

url = "https://store.steampowered.com/api/appdetails?appids=965680&cc=it&l=italian"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

try:
    r = requests.get(url, headers=headers, timeout=10)
    print("STATUS CODE:", r.status_code)
    print("CONTENUTO RICEVUTO:", r.text[:300])
except Exception as e:
    print("ERRORE DI RETE:", e)