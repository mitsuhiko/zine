import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from markupsafe import Markup
from werkzeug.middleware.shared_data import SharedDataMiddleware
from werkzeug.routing import Map
from werkzeug.test import Client, EnvironBuilder
from werkzeug.wrappers import Response as WerkzeugResponse

from zine import _compat, _core


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


def test_url_compatibility_helpers_preserve_multidict_values():
    encoded = _compat.url_encode([("tag", "one"), ("tag", "Grüße")])
    decoded = _compat.url_decode(encoded)

    assert encoded == "tag=one&tag=Gr%C3%BC%C3%9Fe"
    assert decoded.getlist("tag") == ["one", "Grüße"]
    assert _compat.url_encode(None) == ""
    assert _compat.url_quote("post title") == "post%20title"
    assert _compat.url_unquote("Gr%C3%BC%C3%9Fe") == "Grüße"


def test_html_builder_escapes_content_and_normalizes_attributes():
    rendered = _compat.html.label(
        Markup("<strong>Name</strong>"),
        for_="title",
        class_="field",
    )
    checkbox = _compat.html.input(
        type="checkbox", value='a&"b', checked=True, disabled=False
    )

    assert rendered == (
        '<label for="title" class="field"><strong>Name</strong></label>'
    )
    assert checkbox == (
        '<input type="checkbox" value="a&amp;&#34;b" checked="checked">'
    )
    assert _compat.escape('<script>"x"</script>') == (
        "&lt;script&gt;&#34;x&#34;&lt;/script&gt;"
    )


def test_modern_werkzeug_local_manager_cleanup():
    from zine.utils import local, local_manager

    local.request = "request"
    assert local.request == "request"
    assert not hasattr(local_manager, "get_ident")
    local_manager.cleanup()
    with pytest.raises(AttributeError):
        local.request


def test_routing_map_matches_and_builds_core_urls():
    from zine.urls import make_urls

    app = SimpleNamespace(
        cfg={
            "fixed_url_date_digits": True,
            "blog_url_prefix": "",
            "admin_url_prefix": "/admin",
            "account_url_prefix": "/account",
            "profiles_url_prefix": "/authors",
            "category_url_prefix": "/categories",
            "tags_url_prefix": "/tags",
        }
    )
    adapter = Map(make_urls(app)).bind("example.com")

    assert adapter.match("/account/login") == ("account/login", {})
    assert adapter.build("blog/index", {"page": 1}) == "/"


def test_redirect_helpers_reject_external_targets(monkeypatch):
    app = SimpleNamespace(
        cfg={"blog_url": "https://example.com/blog/", "force_https": False}
    )
    request = SimpleNamespace(
        app=app,
        environ={"wsgi.url_scheme": "http"},
        path="/blog/current",
        values={},
        args={},
    )
    _stub(
        monkeypatch,
        "zine.application",
        get_application=lambda: app,
        get_request=lambda: request,
        url_for=lambda endpoint, **values: "/blog/target",
    )
    http = _load(monkeypatch, "_zine_test_http", "zine/utils/http.py")

    response = http.redirect("next")
    assert response.status_code == 302
    assert response.headers["Location"] == "http://example.com/blog/next"
    assert http.redirect_to("blog/index").headers["Location"] == "/blog/target"
    with pytest.raises(http.BadRequest):
        http.redirect("https://other.example/path")


def test_shared_data_middleware_serves_static_files(tmp_path):
    (tmp_path / "hello.txt").write_text("Hello middleware", encoding="utf-8")
    middleware = SharedDataMiddleware(
        lambda environ, start_response: WerkzeugResponse("missing", 404)(
            environ, start_response
        ),
        {"/shared": str(tmp_path)},
    )
    client = Client(middleware, WerkzeugResponse)

    response = client.get("/shared/hello.txt")
    try:
        assert response.status_code == 200
        assert response.get_data(as_text=True) == "Hello middleware"
    finally:
        response.close()


def _load_application(monkeypatch):
    class Query:
        @staticmethod
        def get_nobody():
            return "anonymous"

    db = SimpleNamespace(eagerload=lambda *args: None)
    _stub(monkeypatch, "sqlalchemy.exceptions", SQLAlchemyError=RuntimeError)
    _stub(monkeypatch, "zine.database", db=db, cleanup_session=lambda: None)
    _stub(monkeypatch, "zine.cache", get_cache=lambda app: None)
    _stub(monkeypatch, "zine.i18n")
    _stub(monkeypatch, "zine.utils.exceptions", UserException=Exception)
    _stub(monkeypatch, "zine.utils.log")
    _stub(monkeypatch, "zine.utils.net", NetException=RuntimeError)
    _stub(monkeypatch, "zine.utils.http", make_external_url=lambda value: value)
    _stub(monkeypatch, "zine.models", User=SimpleNamespace(query=Query()))
    return _load(monkeypatch, "_zine_test_application", "zine/application.py")


def test_application_request_response_and_url_building(monkeypatch):
    application = _load_application(monkeypatch)
    app = SimpleNamespace(
        database_engine=object(),
        cfg={"session_cookie_name": "session"},
        secret_key=b"secret",
    )
    environ = EnvironBuilder(
        path="/posts", query_string={"page": "2"}, method="GET"
    ).get_environ()
    environ["ZINE_BEHIND_PROXY"] = "1"

    request = application.Request(environ, app)
    response = application.Response("Grüße")

    assert request.path == "/posts"
    assert request.args["page"] == "2"
    assert request.user == "anonymous"
    assert request.is_behind_proxy
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert response.get_data(as_text=True) == "Grüße"

    adapter = SimpleNamespace(
        build=lambda endpoint, values, force_external=False: "/post/hello"
    )
    monkeypatch.setattr(_core, "_application", SimpleNamespace(url_adapter=adapter))
    assert application.url_for("blog/post", _anchor="Grüße") == (
        "/post/hello#Gr%C3%BC%C3%9Fe"
    )
