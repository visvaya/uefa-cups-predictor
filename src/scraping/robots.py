"""robots.txt rules as RFC 9309 defines them.

urllib.robotparser is not used: it reads `*` and `$` in paths literally, applies the first matching rule instead of
the longest one, and matches user agents by substring.
"""

import re
import string
from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import quote, urlsplit


@dataclass(frozen=True)
class Rule:
    allow: bool
    pattern: str  # normalised path pattern; `*` matches any sequence, a final `$` anchors the end


Rules = tuple[Rule, ...]
ALLOW_ALL: Rules = ()
DISALLOW_ALL: Rules = (Rule(allow=False, pattern="/"),)
# Kept as they are when normalising: reserved characters (RFC 3986), whose encoded and plain forms differ in meaning,
# and "%" itself; everything else is compared in one encoded form, so "%7E" equals "~" and "%3c" equals "<"
SAFE_CHARACTERS = "/?#[]@!$&'()*+,;=:%"


UNRESERVED = frozenset(string.ascii_letters + string.digits + "-._~")
ESCAPE = re.compile("%([0-9A-Fa-f]{2})")


def normalise(text: str) -> str:
    """Decodes escapes of unreserved characters only; other escapes keep their meaning, in uppercase hex."""

    def unescape(match: re.Match[str]) -> str:
        char = chr(int(match.group(1), 16))
        return char if char in UNRESERVED else "%" + match.group(1).upper()

    return quote(ESCAPE.sub(unescape, text), safe=SAFE_CHARACTERS)


def product_token(user_agent: str) -> str:
    """The name part of a user agent ("uefa-cups-predictor" from "uefa-cups-predictor/0.1 (...)"), lowercase."""
    return user_agent.split("/")[0].strip().lower()


def records(robots_txt: str) -> Iterator[tuple[str, str]]:
    """(lowercase key, value) of every "key: value" line, comments removed."""
    for line in robots_txt.splitlines():
        key, colon, value = line.split("#", 1)[0].partition(":")
        if colon:
            yield key.strip().lower(), value.strip()


def groups(robots_txt: str) -> dict[str, list[Rule]]:
    """Rules per product token; groups naming the same token are combined, consecutive User-agent lines share one."""
    rules_by_agent: dict[str, list[Rule]] = {}
    agents: list[str] = []
    in_rules = False
    for key, value in records(robots_txt):
        if key == "user-agent":
            agents = [product_token(value)] if in_rules else [*agents, product_token(value)]
            in_rules = False
            rules_by_agent.setdefault(agents[-1], [])
        elif key in ("allow", "disallow") and agents:
            in_rules = True
            # An empty value disallows (or allows) nothing
            rule = [Rule(allow=key == "allow", pattern=normalise(value))] if value else []
            for agent in agents:
                rules_by_agent[agent] += rule
    return rules_by_agent


def parse_robots(robots_txt: str, user_agent: str) -> Rules:
    """The rules of the groups naming `user_agent`'s product token, else of the `*` groups, else none."""
    rules_by_agent = groups(robots_txt)
    token = product_token(user_agent)
    return tuple(rules_by_agent[token] if token in rules_by_agent else rules_by_agent.get("*", []))


def matches(pattern: str, path: str) -> bool:
    anchored = pattern.endswith("$")
    body = pattern.removesuffix("$")
    regex = ".*".join(re.escape(part) for part in body.split("*"))
    return (re.fullmatch if anchored else re.match)(regex, path) is not None


def is_allowed(rules: Rules, url: str) -> bool:
    """Whether `url` may be fetched: the longest matching rule decides, Allow wins a tie, no match allows."""
    parts = urlsplit(url)
    path = normalise(parts.path or "/") + (f"?{normalise(parts.query)}" if parts.query else "")
    matching = [rule for rule in rules if matches(rule.pattern, path)]
    if not matching:
        return True
    return max(matching, key=lambda rule: (len(rule.pattern), rule.allow)).allow
