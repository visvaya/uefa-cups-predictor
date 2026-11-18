"""The results page: both tabs, the explanations and tab titles for the page script, and the footer, in the template.

The template has four placeholders: `{{VIEWS}}`, `{{TERMS_JSON}}`, `{{TAB_TITLES_JSON}}` and `{{FOOTER}}`.
"""

import json

from analyzer.page.model import PageData
from analyzer.page.render_cups import cups_view
from analyzer.page.render_parts import bind_short_words
from analyzer.page.render_sr import sr_days, sr_view
from analyzer.page.texts import (
    FOOTER_GAMBLING,
    FOOTER_INDEPENDENCE,
    FOOTER_LICENCE,
    FOOTER_TOP,
    GENERATED,
    TAB_CUPS,
    TAB_SR,
    TAB_SR_EMPTY,
    TERMS,
    footer_sources,
    short_date_span,
    stamp,
)


def _script_json(value: object) -> str:
    """JSON for a script element: every `</` is escaped, so no text can close the element."""
    return json.dumps(value, ensure_ascii=False).replace("</", "<" + chr(92) + "/")


def _tab_titles(data: PageData) -> dict[str, str]:
    days = sr_days(data.sr_rows)
    return {"sr": TAB_SR.format(days=short_date_span(*days)) if days else TAB_SR_EMPTY, "full": TAB_CUPS}


def _footer(data: PageData) -> str:
    sources = f"{footer_sources(data.scraped_at)} {GENERATED.format(stamp=stamp(data.generated_at))}"
    small = "\n".join(
        f"<p><small>{text}</small></p>" for text in (sources, FOOTER_GAMBLING, FOOTER_INDEPENDENCE, FOOTER_LICENCE)
    )
    return f"<p>{FOOTER_TOP}</p>\n{small}"


def render_page(data: PageData, template: str) -> str:
    """The page as HTML; the views go in last, so nothing in the inputs can fill another placeholder."""
    views = bind_short_words(f"{sr_view(data)}\n{cups_view(data.cups)}")
    return (
        template.replace("{{TERMS_JSON}}", _script_json(TERMS))
        .replace("{{TAB_TITLES_JSON}}", _script_json(_tab_titles(data)))
        .replace("{{FOOTER}}", bind_short_words(_footer(data)))
        .replace("{{VIEWS}}", views)
    )
