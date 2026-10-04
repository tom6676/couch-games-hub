import urllib.parse
from config import AFFILIATE_TAG_G2A

def get_g2a_deal(game_title):
    """
    Costruisce l'URL di ricerca G2A con tracking Goldmine affiliato.
    """
    search_query = f"{game_title} Steam Key"
    encoded_title = urllib.parse.quote_plus(search_query)
    
    # URL di ricerca con parametro referral Goldmine
    g2a_affiliate_url = f"https://www.g2a.com/search?query={encoded_title}&ref={AFFILIATE_TAG_G2A}"
    
    return {
        "store": "G2A Reseller",
        "url": g2a_affiliate_url
    }