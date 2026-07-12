"""Small compatibility helpers for APIs removed from modern Werkzeug."""

from html import unescape
from urllib.parse import parse_qsl, quote, unquote, urlencode

from markupsafe import Markup
from werkzeug.datastructures import MultiDict


_VOID_ELEMENTS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)


def escape(value, quote=True):
    """Escape a value for HTML and return a :class:`~markupsafe.Markup`."""
    if hasattr(value, "__html__"):
        return Markup(value.__html__())
    value = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(
        ">", "&gt;"
    )
    if quote:
        value = value.replace('"', "&#34;").replace("'", "&#39;")
    return Markup(value)


def url_quote(value, charset="utf-8", errors="strict", safe="/:"):
    if isinstance(value, bytes):
        value = value.decode(charset, errors)
    return quote(str(value), safe=safe, encoding=charset, errors=errors)


def url_unquote(value, charset="utf-8", errors="replace"):
    if isinstance(value, bytes):
        value = value.decode("ascii")
    return unquote(value, encoding=charset, errors=errors)


def url_encode(obj, charset="utf-8", encode_keys=False, sort=False, key=None):
    if obj is None:
        return ""
    if hasattr(obj, "items"):
        try:
            items = list(obj.items(multi=True))
        except TypeError:
            items = list(obj.items())
    else:
        items = list(obj)
    if sort:
        items.sort(key=key)
    return urlencode(items, doseq=True, encoding=charset)


def url_decode(
    value, charset="utf-8", errors="replace", separator="&", cls=MultiDict
):
    if isinstance(value, bytes):
        value = value.decode("ascii")
    items = parse_qsl(
        value,
        keep_blank_values=True,
        encoding=charset,
        errors=errors,
        separator=separator,
    )
    return cls(items)


class _HTMLBuilder:
    def __getattr__(self, tag):
        tag = tag.rstrip("_").replace("_", "-")

        def build(*children, **attributes):
            rendered_attributes = []
            for name, value in attributes.items():
                name = name.rstrip("_").replace("_", "-")
                if value is None or value is False:
                    continue
                if value is True:
                    value = name
                rendered_attributes.append(
                    Markup(' %s="%s"') % (name, escape(value, quote=True))
                )
            start = Markup("<%s%s>") % (tag, Markup().join(rendered_attributes))
            if tag in _VOID_ELEMENTS:
                return start
            body = Markup().join(
                child if hasattr(child, "__html__") else escape(child, quote=False)
                for child in children
            )
            return start + body + Markup("</%s>") % tag

        return build


html = _HTMLBuilder()
