import requests

query_url = (
    "https://store.steampowered.com/search/results/"
    "?query=&start=0&count=10&dynamic_data=&sort_by=_ASC"
    "&category2=24%2C39"
    "&specials=1"
    "&cc=it&l=italian&json=1"
)
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

r = requests.get(query_url, headers=headers, timeout=10).json()
print("Chiavi presenti nel JSON:", list(r.keys()))
print("Total results:", r.get("total_count"))
if "items" in r:
    print("Numero items:", len(r["items"]))
    if len(r["items"]) > 0:
        print("Esempio primo item:", r["items"][0])