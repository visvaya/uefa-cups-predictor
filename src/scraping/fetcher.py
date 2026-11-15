import logging
from typing import ClassVar
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://www.soccer-rating.com"
ALLOWED_HOSTS = frozenset({"www.soccer-rating.com", "soccer-rating.com"})


def resolve_url(url_path: str) -> str | None:
    """Turns a page link into the URL to fetch, or None when it leaves https://soccer-rating.com.

    Links come from the fetched pages, so an absolute URL must not send requests anywhere else.
    """
    url = url_path if urlsplit(url_path).scheme else BASE_URL + "/" + url_path.lstrip("/")
    parts = urlsplit(url)
    return url if parts.scheme == "https" and parts.hostname in ALLOWED_HOSTS else None


class SoccerRatingFetcher:
    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,pl;q=0.8",
    }

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def fetch(self, url_path: str) -> str | None:
        """
        Fetches a page from soccer-rating.com.
        url_path can be a full URL or a relative path.
        """
        url = resolve_url(url_path)
        if url is None:
            logger.warning(f"Skipping {url_path}: not an https URL on soccer-rating.com")
            return None

        try:
            logger.info(f"Fetching {url}...")
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
