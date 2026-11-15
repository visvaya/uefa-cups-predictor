import logging
from typing import ClassVar
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://www.soccer-rating.com"
ALLOWED_HOSTS = frozenset({"www.soccer-rating.com", "soccer-rating.com"})
MAX_REDIRECTS = 5


def resolve_url(link: str, base: str = BASE_URL + "/") -> str | None:
    """Turns a page link or redirect target into the URL to fetch, or None when it leaves https://soccer-rating.com.

    Links and redirects come from the fetched pages, so they must not send requests anywhere else. Characters that
    URL parsers disagree on are rejected, and the URL is rebuilt from the checked parts, so the HTTP client cannot
    read a different host than this check did.
    """
    link = link.strip()  # browsers ignore whitespace around an href
    if any(char == chr(92) or char.isspace() or not char.isprintable() for char in link):
        return None
    try:
        parts = urlsplit(urljoin(base, link))
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS or parts.username or parts.password:
        return None
    if port not in (None, 443):
        return None
    return urlunsplit(("https", parts.hostname, parts.path or "/", parts.query, ""))


class SoccerRatingFetcher:
    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
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
        target, url = url_path, resolve_url(url_path)
        try:
            # Redirects are followed by hand so that every hop passes the same host check.
            for _ in range(MAX_REDIRECTS + 1):
                if url is None:
                    logger.warning(f"Skipping {target}: not an https URL on soccer-rating.com")
                    return None
                logger.info(f"Fetching {url}...")
                response = self.session.get(url, timeout=self.timeout, allow_redirects=False)
                if not response.is_redirect:
                    response.raise_for_status()
                    return response.text
                target = response.headers["location"]
                url = resolve_url(target, base=url)
            logger.error(f"Too many redirects for {url_path}")
            return None
        # ValueError: requests parses a redirect target even with allow_redirects=False and fails on malformed ones.
        except (requests.RequestException, ValueError) as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
