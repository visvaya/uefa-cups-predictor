"""The results page: both tabs, the explanations and tab titles for the page script, and the footer, in the templates.

`page.html.j2` is the skeleton; the tabs and the footer are rendered first, so their text can be typeset.
"""

import json

from jinja2 import Environment
from markupsafe import Markup

from analyzer.page.model import PageData
from analyzer.page.render_cups import cups_view
from analyzer.page.render_parts import typeset, typeset_html
from analyzer.page.render_sr import sr_days, sr_view
from analyzer.page.texts import (
    GENERATED,
    NBSP,
    TAB_CUPS,
    TAB_SR,
    TAB_SR_EMPTY,
    TERMS,
    footer_sources,
    short_date_span,
    stamp,
)


def _markup(html: str) -> Markup:
    """Text that is already page markup, so autoescape leaves it: rendered tabs, or JSON with its `</` escaped."""
    return Markup(html)  # noqa: S704 (only rendered, escaped templates and escaped script JSON come here)


def _script_json(value: object) -> Markup:
    """JSON for a script element: every `</` is escaped, so no text can close the element."""
    return _markup(json.dumps(value, ensure_ascii=False).replace("</", "<" + chr(92) + "/"))


def _tab_titles(data: PageData) -> dict[str, str]:
    days = sr_days(data.sr_rows)
    return {"sr": TAB_SR.format(days=short_date_span(*days)) if days else TAB_SR_EMPTY, "full": TAB_CUPS}


def render_page(data: PageData, env: Environment) -> str:
    """The page as HTML, rendered with the templates of `env` (see `page_environment`)."""
    sr = env.get_template("sr.html.j2").render(sr_view(data))
    cups = env.get_template("cups.html.j2").render(cups_view(data.cups))
    footer = env.get_template("footer.html.j2").render(
        sources=footer_sources(data.scraped_at), generated=GENERATED.format(stamp=stamp(data.generated_at))
    )
    # The page script shows the explanations as plain text, so they take the characters, not entities
    terms = {key: (typeset(title, NBSP), typeset(text, NBSP)) for key, (title, text) in TERMS.items()}
    return env.get_template("page.html.j2").render(
        views=_markup(typeset_html(sr + cups)),
        footer=_markup(typeset_html(footer)),
        terms_json=_script_json(terms),
        tab_titles_json=_script_json(_tab_titles(data)),
    )
