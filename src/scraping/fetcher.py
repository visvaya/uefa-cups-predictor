import logging
from typing import ClassVar
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://www.soccer-rating.com"
ALLOWED_HOSTS = frozenset({"www.soccer-rating.com", "soccer-rating.com"})
MAX_REDIRECTS = 5
ROBOTS_PATH = "/robots.txt"
# Names the tool and where to read about it, so the site can tell who sends the requests
DEFAULT_USER_AGENT = "uefa-cups-predictor/0.1 (+https://github.com/visvaya/uefa-cups-predictor)"


def robots_rules(robots_txt: str) -> RobotFileParser:
    """Parsed robots.txt rules; an empty text allows everything."""
    rules = RobotFileParser()
    rules.parse(robots_txt.splitlines())
    return rules


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
        self.robots: RobotFileParser | None = None

    def fetch(self, url_path: str) -> str | None:
        """Fetches a page from soccer-rating.com (a full URL or a relative path) unless robots.txt disallows it.

        robots.txt is read once, on the first fetch; when it cannot be read, every path is allowed.
        """
        if self.robots is None:
            robots_txt = self._get(ROBOTS_PATH, robots_rules(""))
            if robots_txt is None:
                logger.warning("Could not read robots.txt; continuing without its rules")
            self.robots = robots_rules(robots_txt or "")
        return self._get(url_path, self.robots)

    def _get(self, url_path: str, robots: RobotFileParser) -> str | None:
        target, url = url_path, resolve_url(url_path)
        try:
            # Redirects are followed by hand so that every hop passes the same host check.
            for _ in range(MAX_REDIRECTS + 1):
                if url is None:
                    logger.warning(f"Skipping {target}: not an https URL on soccer-rating.com")
                    return None
                if not robots.can_fetch(self.user_agent, url):
                    logger.warning(f"Skipping {url}: disallowed by robots.txt")
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
