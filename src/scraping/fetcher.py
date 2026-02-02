import requests
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class SoccerRatingFetcher:
    BASE_URL = "https://www.soccer-rating.com"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,pl;q=0.8",
    }

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def fetch(self, url_path: str) -> Optional[str]:
        """
        Fetches a page from soccer-rating.com.
        url_path can be a full URL or a relative path.
        """
        if url_path.startswith("http"):
            url = url_path
        else:
            # Ensure relative path starts with /
            if not url_path.startswith("/"):
                url_path = "/" + url_path
            url = self.BASE_URL + url_path

        try:
            logger.info(f"Fetching {url}...")
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
