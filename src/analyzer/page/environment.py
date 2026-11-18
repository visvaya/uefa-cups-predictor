"""The results page's Jinja2 environment: it reads every template file up front, so it lives outside the page logic
that does no I/O, and `render_page` renders from memory."""

from importlib.resources import files

from jinja2 import DictLoader, Environment, StrictUndefined

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
    page needs the whitespace the other way. The templates are read here into a `DictLoader`, which never checks the
    files again.
    """
    folder = files("analyzer.page") / "templates"
    sources = {item.name: item.read_text(encoding="utf-8") for item in folder.iterdir() if item.name.endswith(".j2")}
    env = Environment(
        loader=DictLoader(sources),
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
