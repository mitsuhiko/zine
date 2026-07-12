import sys
from http.cookies import SimpleCookie
from time import time
from types import ModuleType, SimpleNamespace

from cachelib import FileSystemCache, NullCache, SimpleCache
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request, Response

from zine import cache
from zine.session import SecureCookie


def _request(path="/", query_string=None, cookie=None, headers=None):
    headers = dict(headers or ())
    if cookie is not None:
        headers["Cookie"] = cookie
    environ = EnvironBuilder(
        path=path, query_string=query_string, headers=headers
    ).get_environ()
    return Request(environ)


def _cookie_value(response, name):
    cookie = SimpleCookie()
    cookie.load(response.headers["Set-Cookie"])
    return cookie[name].value


def test_secure_cookie_round_trip_and_mutation_tracking():
    session = SecureCookie.load_cookie(_request(), "session", b"secret")
    assert not session.should_save

    session["uid"] = 42
    session.setdefault("messages", []).append("Grüße")
    assert session.should_save

    response = Response()
    session.save_cookie(response, "session", max_age=3600)
    assert not session.should_save
    value = _cookie_value(response, "session")

    loaded = SecureCookie.load_cookie(
        _request(cookie="session=" + value), "session", b"secret"
    )
    assert loaded == {"uid": 42, "messages": ["Grüße"]}
    assert not loaded.should_save
    loaded.setdefault("messages", []).append("again")
    assert loaded.should_save


def test_secure_cookie_rejects_tampering_and_expired_sessions():
    session = SecureCookie({"uid": 42}, b"secret")
    response = Response()
    session.save_cookie(response, "session")
    value = _cookie_value(response, "session")

    tampered = value[:-1] + ("a" if value[-1] != "a" else "b")
    assert SecureCookie.load_cookie(
        _request(cookie="session=" + tampered), "session", b"secret"
    ) == {}

    expired_response = Response()
    session.save_cookie(
        expired_response, "session", session_expires=time() - 1
    )
    expired = _cookie_value(expired_response, "session")
    assert SecureCookie.load_cookie(
        _request(cookie="session=" + expired), "session", b"secret"
    ) == {}


def test_cache_factories_use_cachelib(tmp_path):
    app = SimpleNamespace(
        instance_folder=str(tmp_path),
        cfg={
            "cache_system": "simple",
            "cache_timeout": 60,
            "filesystem_cache_path": "cache",
            "memcached_servers": [],
        },
    )
    simple = cache.get_cache(app)
    assert isinstance(simple, SimpleCache)
    simple.set("key", "value")
    assert simple.get("key") == "value"

    app.cfg["cache_system"] = "filesystem"
    filesystem = cache.get_cache(app)
    assert isinstance(filesystem, FileSystemCache)
    filesystem.set("key", {"value": 42})
    assert filesystem.get("key") == {"value": 42}


def test_null_cache_disables_cache_context():
    request = SimpleNamespace(
        app=SimpleNamespace(
            cache=NullCache(), cfg={"enable_eager_caching": True}
        ),
        user=SimpleNamespace(is_somebody=False),
        method="GET",
    )
    assert cache.get_cache_context((), request=request) == (request, False)


def test_result_cache_preserves_decorator_interface():
    from zine.utils import local, local_manager

    request = SimpleNamespace(
        app=SimpleNamespace(
            cache=SimpleCache(default_timeout=60),
            cfg={"enable_eager_caching": True},
        ),
        user=SimpleNamespace(is_somebody=False),
        method="GET",
    )
    local.request = request
    calls = []

    @cache.result("sum")
    def add(left, right=0):
        calls.append((left, right))
        return left + right

    try:
        assert add(2, right=3) == 5
        assert add(2, right=3) == 5
        assert calls == [(2, 3)]
    finally:
        local_manager.cleanup()


def test_response_cache_uses_stable_keys_and_fresh_responses(monkeypatch):
    application = ModuleType("zine.application")
    application.Response = Response
    monkeypatch.setitem(sys.modules, "zine.application", application)

    app = SimpleNamespace(
        cache=SimpleCache(default_timeout=60),
        cfg={"enable_eager_caching": True},
    )
    calls = []

    @cache.response()
    def view(request):
        calls.append(request.full_path)
        return Response("payload:" + request.args.get("page", ""))

    def make_request(page, headers=None):
        request = _request(
            "/entries", query_string={"page": page}, headers=headers
        )
        request.app = app
        request.user = SimpleNamespace(is_somebody=False)
        return request

    first = view(make_request("1"))
    second = view(make_request("1"))
    different_query = view(make_request("2"))

    assert first.get_data(as_text=True) == "payload:1"
    assert second.get_data(as_text=True) == "payload:1"
    assert different_query.get_data(as_text=True) == "payload:2"
    assert calls == ["/entries?page=1", "/entries?page=2"]
    assert first is not second

    etag = first.headers["ETag"]
    conditional = view(make_request("1", {"If-None-Match": etag}))
    assert conditional.status_code == 304
    assert second.status_code == 200
