import pickle
import struct
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from babel.messages import Catalog
from babel.messages.mofile import write_mo
from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader
from markupsafe import Markup

from zine import i18n


ROOT = Path(__file__).resolve().parents[1]


def _write_catalog(root, locale, messages, client_ids=(), footer=True):
    catalog = Catalog(locale=locale)
    by_id = {}
    for message_id, string in messages:
        by_id[message_id] = catalog.add(message_id, string)

    stream = BytesIO()
    write_mo(stream, catalog)
    if footer:
        offset = stream.tell()
        pickle.dump([by_id[message_id] for message_id in client_ids], stream, 2)
        stream.write(b"ZINE")
        stream.write(struct.pack("!I", offset))

    folder = root / locale
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "messages.mo").write_bytes(stream.getvalue())


def test_gettext_catalog_and_client_metadata_round_trip(tmp_path):
    _write_catalog(
        tmp_path,
        "de",
        [
            ("Hello", "Hallo"),
            (("apple", "apples"), ("Apfel", "Äpfel")),
            ("Client message", "Client-Nachricht"),
        ],
        client_ids=("Client message",),
    )

    translations = i18n.ZineTranslations.load(tmp_path, "de")
    assert translations.gettext("Hello") == "Hallo"
    assert translations.ngettext("apple", "apples", 1) == "Apfel"
    assert translations.ngettext("apple", "apples", 2) == "Äpfel"
    assert {message.id for message in translations.client_keys} == {
        "Client message"
    }
    assert translations.plural_expr


def test_standard_mo_without_zine_footer_is_supported(tmp_path):
    _write_catalog(tmp_path, "de", [("Hello", "Hallo")], footer=False)

    translations = i18n.ZineTranslations.load(tmp_path, "de")
    assert translations.gettext("Hello") == "Hallo"
    assert translations.client_keys == []


def test_core_and_plugin_catalogs_merge(tmp_path):
    core_path = tmp_path / "core"
    plugin_path = tmp_path / "plugin"
    _write_catalog(core_path, "de", [("Hello", "Hallo")])
    _write_catalog(plugin_path, "de", [("Plugin", "Erweiterung")])

    translations = i18n.ZineTranslations.load(core_path, "de")
    translations.merge(i18n.ZineTranslations.load(plugin_path, "de"))

    assert translations.gettext("Hello") == "Hallo"
    assert translations.gettext("Plugin") == "Erweiterung"


def test_null_catalog_fallback_and_localized_language_names(monkeypatch, tmp_path):
    _write_catalog(tmp_path, "de", [("Hello", "Hallo")])
    german = i18n.ZineTranslations.load(tmp_path, "de")
    translations = i18n.ZineNullTranslations(locale="de")
    translations.merge(german)
    assert translations.gettext("Hello") == "Hallo"

    monkeypatch.setattr(i18n, "LOCALE_PATH", str(tmp_path))
    monkeypatch.setattr(i18n, "get_locale", lambda: i18n.Locale("de"))
    languages = dict(i18n.list_languages(self_translated=True))
    assert languages["en"] == "Englisch"
    assert languages["de"] == "Deutsch"


def test_lazy_translation_proxy_is_text_like_and_escaped(monkeypatch):
    monkeypatch.setattr(i18n, "get_translations", lambda: None)
    lazy = i18n.lazy_gettext("<strong>Hello</strong>")

    assert str(lazy) == "<strong>Hello</strong>"
    assert format(lazy, ">24").endswith("<strong>Hello</strong>")
    assert lazy.upper() == "<STRONG>HELLO</STRONG>"

    env = Environment(autoescape=True)
    template = env.from_string("{{ lazy }} {{ safe }}")
    rendered = template.render(lazy=lazy, safe=Markup("<em>safe</em>"))
    assert rendered == (
        "&lt;strong&gt;Hello&lt;/strong&gt; <em>safe</em>"
    )


def _template_environment(loader):
    env = Environment(
        loader=loader,
        extensions=["jinja2.ext.i18n"],
        autoescape=False,
    )
    env.install_null_translations(newstyle=False)
    env.filters.update(
        json=str,
        datetimeformat=str,
        dateformat=str,
        monthformat=str,
        timedeltaformat=str,
    )
    return env


def test_all_bundled_templates_compile():
    env = _template_environment(None)
    templates = sorted((ROOT / "zine").rglob("*.html"))
    assert templates
    for filename in templates:
        env.from_string(filename.read_text(encoding="utf-8"))


def test_representative_core_and_setup_templates_render():
    core = _template_environment(FileSystemLoader(ROOT / "zine/templates"))
    rendered = core.get_template("maintenance.html").render()
    assert "Maintenance Mode" in rendered

    setup = _template_environment(
        FileSystemLoader(ROOT / "zine/websetup/templates")
    )
    rendered = setup.get_template("start.html").render(
        current="start",
        prev=None,
        next="database",
        values={},
        languages=[("en", "English"), ("de", "Deutsch")],
        lang="de",
        error=None,
    )
    assert "Welcome To The Zine Setup" in rendered
    assert '<option value="de" selected>' in rendered


def test_representative_admin_and_plugin_templates_render():
    parent = """
        {% block title %}{% endblock %}
        {% block html_head %}{% endblock %}
        {% block contents %}{% endblock %}
    """
    loader = ChoiceLoader(
        [
            DictLoader({"admin/layout.html": parent}),
            FileSystemLoader(ROOT / "zine/templates"),
            FileSystemLoader(ROOT / "zine/plugins/typography/templates"),
        ]
    )
    env = _template_environment(loader)

    form = SimpleNamespace(hidden_fields=Markup('<input type="hidden">'))
    admin = env.get_template("admin/maintenance.html").render(
        form=form, maintenance_mode=False
    )
    assert "Enable maintenance mode" in admin

    class TypographyForm:
        double_opening_quote = staticmethod(lambda **kwargs: "“")
        double_closing_quote = staticmethod(lambda **kwargs: "”")
        single_opening_quote = staticmethod(lambda **kwargs: "‘")
        single_closing_quote = staticmethod(lambda **kwargs: "’")

        def __call__(self, caller=None, **kwargs):
            return Markup("<form>") + caller() + Markup("</form>")

    plugin = env.get_template("admin/typography.html").render(
        form=TypographyForm()
    )
    assert "Typography" in plugin
    assert "<form>" in plugin
