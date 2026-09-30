"""Constants and known season IDs for GameSheet API."""

FIRESTORE_PROJECT = "gamesheet-production"
FIRESTORE_BASE = (
    f"https://firestore.googleapis.com/v1/projects/"
    f"{FIRESTORE_PROJECT}/databases/(default)/documents"
)
API_BASE = "https://gamesheetstats.com/api"
SITE_BASE = "https://gamesheetstats.com"

# gamesheetstats.com sits behind Cloudflare, which 403s the bare `requests`
# User-Agent. A browser UA plus Origin/Referer (Referer is set per season on
# the session) is what the stats site itself sends.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": SITE_BASE,
}

IMAGE_CDN = "https://imagedelivery.net/ErrQpIaCOWR-Tz51PhN1zA"

# Known season IDs by league and year.
# Consuming projects can pass their own — this is just a reference lookup.
KNOWN_SEASONS = {
    "ICSHL":  {"2025-26": "10450", "2026-27": "15154"},
    "SHSHL":  {"2025-26": "11546"},
    "SJHSHL": {"2025-26": "11761"},
    "APAC":   {"2025-26": "11581"},
    "CPIHL":  {"2025-26": "10841"},
}

REQUEST_TIMEOUT = 30  # seconds (unified-games pages can be large)
SEASON_GAMES_CACHE_TTL = 60  # seconds; get_schedule/get_scores share one fetch
MAX_RETRIES = 2
