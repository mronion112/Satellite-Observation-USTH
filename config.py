"""User-configurable settings for the satellite reception scraper."""

TARGET_URL = "https://thailand.wxbunka.com/archive.html"
OUTPUT_DIR = "/home/mronion216/Documents/Onion Code/Project/Satellite-Observation-USTH/dataWeb/ThaiLan"
HTML_FILENAME = "document.html"

OVERWRITE = False
REQUEST_TIMEOUT = (10, 60)
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 1.0
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
