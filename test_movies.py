import requests

url = "https://store.steampowered.com/api/appdetails?appids=1426210&cc=it&l=italian"
headers = {"User-Agent": "Mozilla/5.0"}

r = requests.get(url, headers=headers).json()
first_key = next(iter(r))
movies = r[first_key]["data"].get("movies", [])

print(f"Numero di video trovati: {len(movies)}")
if movies:
    print("\nChiavi del primo movie:", list(movies[0].keys()))
    print("Contenuto 'mp4':", movies[0].get("mp4"))
    print("Contenuto 'webm':", movies[0].get("webm"))