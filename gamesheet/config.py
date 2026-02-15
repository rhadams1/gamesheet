"""Constants and known season IDs for GameSheet API."""

FIRESTORE_PROJECT = "gamesheet-production"
FIRESTORE_BASE = (
    f"https://firestore.googleapis.com/v1/projects/"
    f"{FIRESTORE_PROJECT}/databases/(default)/documents"
)
API_BASE = "https://gamesheetstats.com/api"

IMAGE_CDN = "https://imagedelivery.net/ErrQpIaCOWR-Tz51PhN1zA"

# Known season IDs by league and year.
# Consuming projects can pass their own — this is just a reference lookup.
KNOWN_SEASONS = {
    "ICSHL":  {"2025-26": "10450"},
    "SHSHL":  {"2025-26": "11546"},
    "SJHSHL": {"2025-26": "11761"},
    "APAC":   {"2025-26": "11581"},
    "CPIHL":  {"2025-26": "10841"},
}

REQUEST_TIMEOUT = 10  # seconds
MAX_RETRIES = 2
