"""The results page's Jinja2 environment: it loads the template files, so it lives outside the page logic that does
no I/O and is passed to `render_page`."""

from jinja2 import Environment, PackageLoader, StrictUndefined

from analyzer.page.render_parts import keep_last_words
from analyzer.page.texts import (
    EN_DASH,
    FOOTER_GAMBLING,
    FOOTER_INDEPENDENCE,
    FOOTER_LICENCE,
    FOOTER_TOP,
    HEADS,
    HINT,
    LABELS,
    LEVEL_NAMES,
    MINUS,
    SORT_NAMES,
    SR_NO_DATA,
)


def page_environment() -> Environment:
    """Autoescaping environment with the page's fixed texts as globals and a missing variable as an error.

    `trim_blocks` and `lstrip_blocks` let a block tag stand on its own line; the templates add `+` or `-` where the
    page needs the whitespace the other way.
    """
    env = Environment(
        loader=PackageLoader("analyzer.page", "templates"),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["keep_last_words"] = keep_last_words
    env.globals.update(
        EN_DASH=EN_DASH,
        FOOTER_GAMBLING=FOOTER_GAMBLING,
        FOOTER_INDEPENDENCE=FOOTER_INDEPENDENCE,
        FOOTER_LICENCE=FOOTER_LICENCE,
        FOOTER_TOP=FOOTER_TOP,
        HEADS=HEADS,
        HINT=HINT,
        LABELS=LABELS,
        LEVEL_NAMES=LEVEL_NAMES,
        MINUS=MINUS,
        SORT_NAMES=SORT_NAMES,
        SR_NO_DATA=SR_NO_DATA,
    )
    return env
