import html
import importlib.util
import runpy
import sys
import textwrap
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _stub(monkeypatch, name, **attributes):
    module = ModuleType(name)
    module.__dict__.update(attributes)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load(monkeypatch, name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def zeml(monkeypatch):
    datastructures = runpy.run_path(str(ROOT / "zine/utils/datastructures.py"))
    log = ModuleType("log")
    log.exception = lambda *args, **kwargs: None
    _stub(
        monkeypatch,
        "werkzeug",
        escape=lambda value, quote=False: html.escape(str(value), quote=quote),
    )
    _stub(monkeypatch, "zine.i18n", _=lambda value: value)
    _stub(monkeypatch, "zine.utils", log=log)
    _stub(
        monkeypatch,
        "zine.utils.text",
        wrap=lambda value, width: "\n".join(textwrap.wrap(value, width)),
    )
    _stub(
        monkeypatch,
        "zine.utils.datastructures",
        OrderedDict=datastructures["OrderedDict"],
    )
    return _load(monkeypatch, "_zine_parser_test_zeml", "zine/utils/zeml.py")


def test_zeml_parses_renders_and_extracts_text(zeml):
    tree = zeml.parse_zeml(
        b'<P title="A &amp; B">Hello <strong>Gr\xc3\xbc\xc3\x9fe</strong>!</P>',
        "post",
    )

    assert tree.to_html() == (
        '<p title="A &amp; B">Hello <strong>Grüße</strong>!</p>'
    )
    assert tree.to_text(simple=True) == "Hello Grüße!"
    assert "**Grüße**" in tree.to_text()
    assert tree.children[0].parent is tree
    assert tree.children[0].children[0].parent is tree.children[0]


def test_html_fragment_parser_handles_malformed_html_and_comments(zeml):
    tree = zeml.parse_html(
        '<P class=x>Hello <em>there</em><!-- ignored -->!</P>tail'.encode()
    )

    assert tree.to_html() == '<p class="x">Hello <em>there</em>!</p>tail'
    assert tree.to_text(simple=True) == "Hello there!tail"


def test_intro_split_keeps_body_tail_and_parent_links(zeml):
    tree = zeml.parse_zeml(
        "<intro>Hello <b>world</b></intro>Body<p>Second</p>", "post"
    )
    intro, body = zeml.split_intro(tree)

    assert intro.to_html() == "Hello <b>world</b>"
    assert body.to_html() == "Body<p>Second</p>"
    assert intro.children[0].parent is intro
    assert body.children[0].parent is body


def test_zeml_extension_receives_isolated_text(zeml):
    class Extension:
        name = "raw"
        is_isolated = True
        is_void = False
        is_block_level = True
        broken_by = None
        attributes = {"class"}

        def process(self, attributes, content, reason):
            element = zeml.Element("pre")
            element.attributes.update(attributes)
            element.text = "%s:%s" % (reason, content)
            return element

    tree = zeml.parse_zeml(
        '<raw class="example">hello <b>unparsed</b></raw>',
        "post",
        [Extension()],
    )

    assert tree.to_html() == (
        '<pre class="example">post:hello &lt;b&gt;unparsed&lt;/b&gt;</pre>'
    )


def test_sanitizer_flattens_unsafe_elements_and_cleans_attributes(zeml):
    tree = zeml.parse_zeml(
        '<p onclick="bad" style="color: red; position: absolute">'
        '<a href="javascript:bad">link</a><script>alert(1)</script></p>',
        "comment",
    )
    zeml.sanitize(tree)

    assert tree.to_html() == '<p style="color: red"><a>link</a>alert(1)</p>'
    assert tree.children[0].children[0].parent is tree.children[0]


def test_query_results_are_repeatable_after_partial_access(zeml):
    tree = zeml.parse_zeml("<div><p>A</p><p>B</p></div><p>C</p>", "post")
    result = tree.query("p")

    assert result.first.text == "A"
    assert [element.text for element in result] == ["A", "B", "C"]
    assert [element.text for element in result] == ["A", "B", "C"]
    assert result[-1].text == "C"


def test_table_text_rendering_uses_python3_iterators(zeml):
    tree = zeml.parse_zeml(
        "<table><tr><td>A</td><td>B</td></tr>"
        "<tr><td>longer</td><td>two</td></tr></table>",
        "post",
    )

    rendered = tree.to_text()
    assert "| A      | B   |" in rendered
    assert "| longer | two |" in rendered


def test_parser_data_generated_by_ported_parser_round_trips(zeml):
    tree = zeml.parse_zeml("Hello <b>world</b>", "post")
    parser_data = {"tree": tree, "options": [1, "two"]}

    serialized = zeml.dump_parser_data(parser_data)
    restored = zeml.load_parser_data(serialized)

    assert restored["tree"] == tree
    assert restored["tree"].children[0].parent is restored["tree"]
    assert restored["options"] == [1, "two"]


def test_plain_text_parser_uses_python3_pottymouth(monkeypatch, zeml):
    _stub(monkeypatch, "zine.i18n", lazy_gettext=lambda value: value)
    _stub(
        monkeypatch,
        "zine.application",
        iter_listeners=lambda event: (),
        get_application=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "zine.utils.zeml", zeml)
    _stub(monkeypatch, "zine.utils.xml", replace_entities=html.unescape)
    parsers = _load(monkeypatch, "_zine_parser_test_parsers", "zine/parsers.py")
    app = SimpleNamespace(cfg={"plaintext_parser_nolinks": False})
    plain_parser = parsers.PlainTextParser(app)

    tree = plain_parser.parse(
        "Hello *world*. Visit https://example.com/", "comment"
    )

    assert "<b>" in tree.to_html()
    assert 'href="https://example.com/"' in tree.to_html()
    assert 'rel="nofollow"' in tree.to_html()
    assert tree.to_text(simple=True) == "Hello world. Visit https://example.com/"
    assert all(child.parent is tree for child in tree.children)

    app.parsers = {"text": plain_parser}
    parsers.get_application = lambda: app
    dispatched = parsers.parse("Grüße".encode(), "text", "post")
    assert dispatched.to_text(simple=True) == "Grüße"
