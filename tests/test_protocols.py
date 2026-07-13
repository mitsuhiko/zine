import threading
import xmlrpc.client
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest
from lxml import etree
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from zine import feeds, pingback, zxa
from zine.importers import feed as feed_importer
from zine.importers import wordpress
from zine.models import COMMENT_MODERATED, STATUS_PUBLISHED
from zine.utils import net
from zine.utils.dates import format_iso8601, parse_iso8601
from zine.utils.xml import AtomFeed, Fault, XMLRPC, dump_xml


def test_atom_and_rss_feeds_generate_valid_xml():
    west = timezone(-timedelta(hours=3, minutes=30))
    published = datetime(2026, 7, 12, 8, 30, tzinfo=west)
    assert feeds.rfc2822_date(published).endswith("-0330")
    assert feeds.rfc3339_date(published).endswith("-03:30")
    assert parse_iso8601("2026") == datetime(2026, 1, 1)
    assert parse_iso8601("2026-07-12T12:30:01.25+02:30") == datetime(
        2026, 7, 12, 10, 0, 1, 250000
    )
    assert format_iso8601(published) == "2026-07-12T12:00:00Z"

    for feed_class, root_tag in (
        (feeds.Atom1Feed, "{http://www.w3.org/2005/Atom}feed"),
        (feeds.Rss201rev2Feed, "rss"),
    ):
        feed = feed_class(
            "Zine & News",
            "https://example.test/ä",
            "Description",
            language="en",
            feed_url="https://example.test/feed",
        )
        feed.add_item(
            "Entry <One>",
            "https://example.test/entry",
            "<p>Body</p>",
            author_name="Alice",
            author_email="alice@example.test",
            pubdate=published,
            unique_id="tag:example.test,2026:entry",
            enclosure=feeds.Enclosure(
                "https://example.test/audio.mp3", 42, "audio/mpeg"
            ),
            categories=("Python",),
        )

        document = feed.writeString("utf-8")
        root = ElementTree.fromstring(document.encode("utf-8"))
        assert root.tag == root_tag
        assert "Zine &amp; News" in document
        assert "%C3%A4" in document


def test_removed_werkzeug_atom_helper_remains_compatible():
    updated = datetime(2026, 7, 12, 10, 30)
    feed = AtomFeed(
        "Compatibility Feed",
        feed_url="https://example.test/feed.atom",
        url="https://example.test/",
        author={"name": "Alice", "email": "alice@example.test"},
    )
    feed.add(
        "Entry",
        "<p>Body</p>",
        content_type="html",
        url="https://example.test/entry",
        id="tag:example.test,2026:entry",
        updated=updated,
        published=updated,
    )

    response = feed.get_response()
    root = ElementTree.fromstring(response.get_data())
    assert root.tag == "{http://www.w3.org/2005/Atom}feed"
    assert root.findtext("{http://www.w3.org/2005/Atom}title") == (
        "Compatibility Feed"
    )
    assert b"&lt;p&gt;Body&lt;/p&gt;" in response.get_data()


def test_xml_dump_and_xmlrpc_round_trip():
    document = dump_xml({"items": [1, "two", None], "enabled": True})
    root = ElementTree.fromstring(document)
    assert root.tag == "envelope"
    assert root.find(".//list") is not None
    assert root.find(".//true") is not None

    service = XMLRPC("test")
    service.register_function(
        lambda value: {"value": value, "missing": None}, "echo"
    )
    payload = xmlrpc.client.dumps(
        (42,), methodname="echo", allow_none=True
    ).encode("utf-8")
    request = Request(EnvironBuilder(
        method="POST", data=payload, content_type="application/xml"
    ).get_environ())
    response = service(request)
    params, method = xmlrpc.client.loads(response.get_data())
    assert method is None
    assert params == ({"value": 42, "missing": None},)

    def fail():
        raise Fault(23, "nope")

    service.register_function(fail)
    payload = xmlrpc.client.dumps((), methodname="fail").encode("utf-8")
    request = Request(EnvironBuilder(method="POST", data=payload).get_environ())
    with pytest.raises(Fault) as error:
        xmlrpc.client.loads(service(request).get_data())
    assert error.value.faultCode == 23


class _HTTPHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _reply(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.server.last_request = (self.command, self.path, self.headers, b"")
        self._reply(200, "Grüße".encode("utf-8"))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.server.last_request = (self.command, self.path, self.headers, body)
        self._reply(201, body)

    def log_message(self, format, *args):
        pass


@pytest.fixture
def http_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HTTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:%d" % server.server_port, server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_network_client_handles_bytes_streams_and_headers(http_server,
                                                           monkeypatch):
    base_url, server = http_server
    monkeypatch.setattr(net, "get_application", lambda: None)

    response = net.open_url(
        base_url + "/hello?name=zine", headers={"X-Zine": "yes"}
    )
    try:
        assert response.status_code == 200
        assert response.get_data() == "Grüße".encode("utf-8")
        assert response.stream.read() == "Grüße".encode("utf-8")
    finally:
        response.close()
    assert server.last_request[0:2] == ("GET", "/hello?name=zine")
    assert server.last_request[2]["X-Zine"] == "yes"

    response = net.open_url(base_url + "/grüße")
    response.close()
    assert server.last_request[1] == "/gr%C3%BC%C3%9Fe"

    upload = BytesIO(b"prefixpayload")
    upload.seek(len(b"prefix"))
    response = net.open_url(
        base_url + "/submit", data=upload,
        headers={"Content-Type": "application/octet-stream"},
    )
    try:
        assert response.status_code == 201
        assert response.get_data() == b"payload"
    finally:
        response.close()
    assert server.last_request[0] == "POST"
    assert server.last_request[3] == b"payload"

    with pytest.raises(net.URLError):
        net.open_url("ftp://example.test/file")


def test_pingback_helpers_decode_http_response_bytes(monkeypatch):
    target = "https://example.test/posts/target"
    body = (
        '<html><head><title>Source &amp; Page</title>'
        '<link rel="pingback" href="https://example.test/rpc"></head>'
        '<body><p>Before <a href="%s">target</a> after.</p></body></html>'
    ) % target
    response = net.URLResponse(
        "https://source.test/post", body.encode("utf-8")
    )
    title, excerpt = pingback.get_excerpt(response, target)
    assert title == "Source & Page"
    assert "target" in excerpt

    called = []

    class PingMethod:
        def ping(self, source_uri, target_uri):
            called.append((source_uri, target_uri))
            return "registered"

    class Proxy:
        pingback = PingMethod()

    monkeypatch.setattr(pingback, "open_url", lambda url: response)
    monkeypatch.setattr(pingback, "ServerProxy", lambda url: Proxy())
    assert pingback.pingback("https://source.test/post", target) == "registered"
    assert called == [("https://source.test/post", target)]

    handled = []
    app = SimpleNamespace(
        cfg={"blog_url": "https://example.test/"},
        url_adapter=SimpleNamespace(
            match=lambda path: ("blog/post", {"slug": "target"})
        ),
        pingback_endpoints={
            "blog/post": lambda response, target_uri, **values: handled.append(
                values["slug"]
            )
        },
        pingback_url_handlers=[],
    )
    monkeypatch.setattr(pingback, "get_application", lambda: app)
    result = pingback.handle_pingback_request(
        "https://source.test/post", target
    )
    assert "endpoint: 'blog/post'" in result
    assert handled == ["target"]


def test_wordpress_importer_accepts_binary_wxr():
    source = b'''<?xml version="1.0" encoding="UTF-8"?>
    <rss xmlns:content="http://purl.org/rss/1.0/modules/content/"
         xmlns:dc="http://purl.org/dc/elements/1.1/"
         xmlns:wp="http://wordpress.org/export/1.0/">
      <channel>
        <title>Imported Blog</title>
        <link>https://wordpress.example/</link>
        <description>A blog</description>
        <language>en</language>
        <item>
          <title>Hello</title>
          <link>https://wordpress.example/hello</link>
          <dc:creator>alice</dc:creator>
          <wp:status>draft</wp:status>
          <wp:post_type>post</wp:post_type>
          <wp:post_name>hello</wp:post_name>
          <wp:post_date_gmt>2026-07-12 10:00:00</wp:post_date_gmt>
          <content:encoded><![CDATA[<p>Hello &amp; goodbye</p>]]></content:encoded>
        </item>
      </channel>
    </rss>'''

    blog = wordpress.parse_feed(BytesIO(source))
    assert blog.title == "Imported Blog"
    assert len(blog.posts) == 1
    assert blog.posts[0].title == "Hello"
    assert "Hello &amp; goodbye" in blog.posts[0].body


def test_zxa_streaming_export_and_atom_import_round_trip(monkeypatch):
    now = datetime(2026, 7, 12, 10, 30)

    class Tree:
        def __init__(self, html):
            self.html = html

        def to_html(self):
            return self.html

    class Count:
        def __init__(self, value):
            self.value = value

        def count(self):
            return self.value

    privilege = SimpleNamespace(name="BLOG_ADMIN")
    user = SimpleNamespace(
        id=1,
        username="alice",
        email="alice@example.test",
        pw_hash="hash-value",
        _display_name="$username",
        display_name="alice",
        real_name="Alice",
        description="Author",
        www="https://alice.example/",
        is_author=True,
        extra={"key": "value"},
        own_privileges=[privilege],
        posts=Count(1),
        comments=Count(1),
    )
    comment = SimpleNamespace(
        id=4,
        author="Visitor",
        email="visitor@example.test",
        www="https://visitor.example/",
        user=None,
        pub_date=now,
        blocked=False,
        is_pingback=False,
        status=COMMENT_MODERATED,
        blocked_msg=None,
        parent_id=None,
        submitter_ip="127.0.0.1",
        body=Tree("<p>Comment</p>"),
        text="Comment",
        parser_data={"parser": "html", "body": None},
    )
    category = SimpleNamespace(
        slug="news", name="News", description="Updates"
    )
    tag = SimpleNamespace(slug="python", name="Python")
    post = SimpleNamespace(
        id=2,
        title="Hello",
        uid="tag:example.test,2026:hello",
        last_update=now,
        pub_date=now,
        author=user,
        slug="hello",
        comments_enabled=False,
        pings_enabled=True,
        status=STATUS_PUBLISHED,
        content_type="entry",
        text="Raw text",
        body=Tree("<p>Body</p>"),
        intro=Tree("<p>Intro</p>"),
        categories=[category],
        tags=[tag],
        parser_data={"parser": "html", "body": None},
        comments=[comment],
    )

    class Query:
        def __init__(self, values):
            self.values = values

        def order_by(self, *args):
            return self

        def __iter__(self):
            return iter(self.values)

        def all(self):
            return list(self.values)

    class Column:
        def desc(self):
            return self

    monkeypatch.setattr(
        zxa, "Post", SimpleNamespace(query=Query([post]), last_update=Column())
    )
    monkeypatch.setattr(zxa, "User", SimpleNamespace(query=Query([user])))
    monkeypatch.setattr(zxa, "emit_event", lambda name: [])
    monkeypatch.setattr(
        zxa, "url_for", lambda obj, _external=False: "https://example.test/hello"
    )

    class Config(dict):
        def export(self):
            return [("blog_title", self["blog_title"])]

    app = SimpleNamespace(
        cfg=Config(
            blog_title="Example",
            blog_tagline="A blog",
            blog_url="https://example.test/",
            language="en",
        )
    )
    response = zxa.export(app)
    assert response.is_streamed
    payload = response.get_data()
    root = etree.fromstring(payload)
    assert root.tag == "{%s}feed" % zxa.ATOM_NS
    assert b"hash-value" not in payload

    importer_app = SimpleNamespace(
        feed_importer_extensions=[feed_importer.ZEAExtension],
        privileges={"BLOG_ADMIN": "admin-marker"},
    )
    monkeypatch.setattr(feed_importer, "get_application", lambda: importer_app)
    blog = feed_importer.parse_feed(BytesIO(payload))

    imported = blog.posts[0]
    assert blog.link == "https://example.test/"
    assert blog.configuration == {"blog_title": "Example"}
    assert imported.slug == "hello"
    assert imported.comments_enabled is False
    assert imported.pings_enabled is True
    assert imported.status == STATUS_PUBLISHED
    assert imported.parser_data["parser"] == "html"
    assert imported.author.pw_hash == "hash-value"
    assert imported.author.extra == {"key": "value"}
    assert "admin-marker" in imported.author.privileges
    assert imported.tags[0].name == "Python"
    assert imported.categories[0].description == "Updates"
    assert imported.comments[0].body == "<p>Comment</p>"
