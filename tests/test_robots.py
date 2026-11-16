import pytest

from scraping.robots import is_allowed, parse_robots

AGENT = "uefa-cups-predictor/0.1 (+https://github.com/visvaya/uefa-cups-predictor)"
SITE = "https://www.soccer-rating.com"
NL = chr(10)

# (robots.txt lines, path, expected): cases from RFC 9309 sections 2.2.2 and 2.2.3
CASES = [
    # `*` matches any sequence of characters
    (["User-agent: *", "Disallow: /chart.pl*"], "/chart.pl?id=1", False),
    (["User-agent: *", "Disallow: /*.php"], "/contact.php", False),
    (["User-agent: *", "Disallow: /*.php"], "/today-prediction", True),
    # `$` anchors the end of the path
    (["User-agent: *", "Disallow: /*.pl$"], "/chart.pl", False),
    (["User-agent: *", "Disallow: /*.pl$"], "/chart.pl?id=1", True),
    # rules are prefixes: no `$`, any continuation matches
    (["User-agent: *", "Disallow: /chart.pl"], "/chart.pl?id=1", False),
    # the longest matching rule wins, whatever the order
    (["User-agent: *", "Disallow: /a", "Allow: /a/b"], "/a/b/c", True),
    (["User-agent: *", "Allow: /a/b", "Disallow: /a"], "/a/c", False),
    # on a tie, Allow wins
    (["User-agent: *", "Disallow: /x", "Allow: /x"], "/x", True),
    # an empty Disallow allows everything
    (["User-agent: *", "Disallow:"], "/anything", True),
    # percent-encoded and plain characters compare equal
    (["User-agent: *", "Disallow: /%7Euser"], "/~user/page", False),
    (["User-agent: *", "Disallow: /a%3cb"], "/a%3Cb", False),
    # comments and other lines are ignored
    (["# comment", "User-agent: * # all", "Crawl-delay: 5", "Disallow: /private # no"], "/private/x", False),
]

# Group selection by product token
GROUP_CASES = [
    # the group naming our product token applies instead of `*`
    (["User-agent: *", "Disallow: /", "", "User-agent: uefa-cups-predictor", "Allow: /"], "/x", True),
    (["User-agent: *", "Allow: /", "", "User-agent: UEFA-Cups-Predictor/2.0", "Disallow: /x"], "/x", False),
    # a token that only contains part of ours is another crawler
    (["User-agent: cups", "Disallow: /", "", "User-agent: *", "Allow: /"], "/x", True),
    # groups naming the same agent are combined
    (["User-agent: *", "Disallow: /a", "", "User-agent: *", "Disallow: /b"], "/b", False),
    # consecutive User-agent lines share one group
    (["User-agent: other", "User-agent: uefa-cups-predictor", "Disallow: /c"], "/c", False),
    # no group applies: everything allowed
    (["User-agent: other", "Disallow: /"], "/x", True),
]


ENCODING_CASES = [
    # an encoded reserved character keeps its meaning: %24 is a literal dollar sign, not the end anchor
    (["User-agent: *", "Disallow: /report%24"], "/report%24", False),
    (["User-agent: *", "Disallow: /report$"], "/report%24", True),
    # escapes of unreserved characters and plain characters compare equal, whatever the hex case
    (["User-agent: *", "Disallow: /%7euser"], "/~user", False),
    (["User-agent: *", "Disallow: /caf%c3%a9/"], "/caf%C3%A9/x", False),
]


@pytest.mark.parametrize(("lines", "path", "allowed"), CASES + GROUP_CASES + ENCODING_CASES)
def test_is_allowed_follows_rfc_9309(lines: list[str], path: str, allowed: bool) -> None:
    assert is_allowed(parse_robots(NL.join(lines), AGENT), SITE + path) is allowed


def test_empty_robots_txt_allows_everything() -> None:
    assert is_allowed(parse_robots("", AGENT), SITE + "/chart.pl")
