import logging
from typing import ClassVar
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

from .robots import ALLOW_ALL, DISALLOW_ALL, Rules, is_allowed, parse_robots

logger = logging.getLogger(__name__)

BASE_URL = "https://www.soccer-rating.com"
ALLOWED_HOSTS = frozenset({"www.soccer-rating.com", "soccer-rating.com"})
MAX_REDIRECTS = 5
ROBOTS_PATH = "/robots.txt"
# Names the tool and where to read about it, so the site can tell who sends the requests
DEFAULT_USER_AGENT = "uefa-cups-predictor/0.1 (+https://github.com/visvaya/uefa-cups-predictor)"


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
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,pl;q=0.8",
    }

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT, timeout: int = 15):
        self.timeout = timeout
        self.user_agent = user_agent
        self.session = requests.Session()
        self.session.headers.update({**self.HEADERS, "User-Agent": user_agent})
        self.robots: Rules | None = None

    def fetch(self, url_path: str) -> str | None:
        """Fetches a page from soccer-rating.com (a full URL or a relative path) unless robots.txt disallows it.

        robots.txt is read once, on the first fetch.
        """
        if self.robots is None:
            self.robots = self._read_robots()
        response = self._response(url_path, self.robots)
        if response is None:
            return None
        if response.status_code >= 400:
            logger.error(f"Error fetching {url_path}: HTTP {response.status_code}")
            return None
        return response.text

    def _read_robots(self) -> Rules:
        """Rules as RFC 9309 reads them: a 4xx answer allows everything; a server error, a network error or a
        redirect that cannot be followed disallows everything, so the run fetches nothing more."""
        response = self._response(ROBOTS_PATH, ALLOW_ALL)
        if response is not None and response.status_code < 500:
            return parse_robots(response.text, self.user_agent) if response.status_code < 400 else ALLOW_ALL
        logger.error("robots.txt is unreachable; fetching nothing from soccer-rating.com in this run")
        return DISALLOW_ALL

    def _response(self, url_path: str, robots: Rules) -> requests.Response | None:
        """The final answer after following redirects on the site, or None when the request fails or is not allowed."""
        target, url = url_path, resolve_url(url_path)
        try:
            # Redirects are followed by hand so that every hop passes the same host check.
            for _ in range(MAX_REDIRECTS + 1):
                if url is None:
                    logger.warning(f"Skipping {target}: not an https URL on soccer-rating.com")
                    return None
                if not is_allowed(robots, url):
                    logger.warning(f"Skipping {url}: disallowed by robots.txt")
                    return None
                logger.info(f"Fetching {url}...")
                response = self.session.get(url, timeout=self.timeout, allow_redirects=False)
                if not response.is_redirect:
                    return response
                target = response.headers["location"]
                url = resolve_url(target, base=url)
            logger.error(f"Too many redirects for {url_path}")
            return None
        # ValueError: requests parses a redirect target even with allow_redirects=False and fails on malformed ones.
        except (requests.RequestException, ValueError) as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
