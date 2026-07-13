import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAMES = [
    "akismet_spam_filter",
    "blogger_feedimport",
    "creole_parser",
    "example_remote_auth",
    "legacy_apis",
    "miniblog_theme",
    "myrtle_theme",
    "pygments_support",
    "rst_parser",
    "typography",
    "vessel_theme",
]


PLUGIN_SCRIPT = r'''
import os
import xmlrpc.client
from io import BytesIO
from pathlib import Path

from werkzeug.test import Client
from werkzeug.wrappers import Response

from zine import _core, get_wsgi_app

instance = Path(os.environ["ZINE_TEST_INSTANCE"])
plugins = os.environ["ZINE_TEST_PLUGINS"].split(",")
client = Client(get_wsgi_app(str(instance)), Response)
finished = client.post("/", data={
    "_startsetup": "1",
    "_lang": "en",
    "database_uri": "sqlite://zine.db",
    "admin_username": "admin",
    "admin_email": "admin@example.test",
    "admin_password": "secret",
    "admin_password2": "secret",
})
assert b"Setup Finished" in finished.data

config = instance / "zine.ini"
config.write_text(
    config.read_text().replace(
        "plugins = vessel_theme", "plugins = " + ", ".join(plugins)
    )
)
remote_admin = {"REMOTE_USER": "admin"}
index = client.get("/", environ_overrides=remote_admin)
assert index.status_code == 200
app = _core._application

assert set(app.plugins) == set(plugins)
for name in plugins:
    plugin = app.plugins[name]
    assert plugin.active, name
    assert plugin.setup_error is None, (name, plugin.setup_error)
    assert plugin.module is not None

# Parser and document-tree plugin output.
from zine.parsers import parse
creole = parse('Hello **there** -- "quote"', "creole", "post").to_html()
assert "<strong>there</strong>" in creole
assert "–" in creole and "“quote”" in creole
rst = parse(
    "Heading\n=======\n\nHello **there**.\n\n* one\n* two",
    "rst",
    "post",
).to_html()
assert "<h1" in rst and "<strong>there</strong>" in rst and "<ul" in rst
rst_source = parse(
    ".. sourcecode:: python\n\n   print('hello')", "rst", "post"
).to_html()
assert "print" in rst_source and 'class="syntax"' in rst_source

pygments = app.plugins["pygments_support"].module
source_extension = next(
    extension for extension in app.markup_extensions
    if extension.name == "sourcecode"
)
highlighted = source_extension.process(
    {"syntax": "python"}, "print('hello')", "post"
).to_html()
assert "highlight" in highlighted or "syntax" in highlighted
assert "print" in highlighted

# Theme discovery and template loading. Clear Jinja's cache because a normal
# theme change reloads the application.
for theme_name, stylesheet in (
    ("vessel", "vessel_theme/style.css"),
    ("myrtle", "myrtle_theme/style.css"),
    ("miniblog", "miniblog_theme/style.css"),
):
    app.theme = app.themes[theme_name]
    app.template_env.globals["theme"] = app.theme
    app.template_env.cache.clear()
    response = client.get("/", environ_overrides=remote_admin)
    assert response.status_code == 200
    assert stylesheet.encode() in response.data

# Restore the configurable theme and render representative plugin pages.
app.theme = app.themes["vessel"]
app.template_env.globals["theme"] = app.theme
app.template_env.cache.clear()
for url, marker in (
    ("/admin/options/theme/configure", b"Configure Vessel Theme"),
    ("/admin/options/pygments", b"Pygments"),
    ("/admin/options/typography", b"Typography"),
    ("/admin/options/akismet", b"Akismet Configuration"),
):
    response = client.get(url, environ_overrides=remote_admin)
    assert response.status_code == 200, url
    assert marker in response.data, url
css = client.get(
    "/_shared/pygments_support/default.css", environ_overrides=remote_admin
)
assert css.status_code == 200 and b"pre" in css.data

# Akismet responses are HTTP bytes but the plugin API is textual.
akismet = app.plugins["akismet_spam_filter"].module
from zine.utils.net import URLResponse
old_open_url = akismet.open_url
akismet.open_url = lambda *args, **kwargs: URLResponse(
    "https://rest.akismet.test/", b"valid\n"
)
try:
    assert akismet.send_request("key", False, {}, "verify-key") == "valid"
finally:
    akismet.open_url = old_open_url

# The legacy XML-RPC API remains callable through every advertised endpoint.
payload = xmlrpc.client.dumps(
    ("admin", "secret"), methodname="wp.getUsersBlogs"
).encode("utf-8")
response = client.post(
    "/_services/wordpress",
    data=payload,
    content_type="application/xml",
    environ_overrides=remote_admin,
)
values, method = xmlrpc.client.loads(response.get_data())
assert method is None
assert values[0][0]["blogName"] == "My Zine Blog"

# Blogger's Atom extension keeps posts, labels, and comments.
from zine.importers.feed import parse_feed
blogger = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:thr="http://purl.org/syndication/thread/1.0" xml:lang="en">
  <title>Blogger Export</title>
  <subtitle>Imported</subtitle>
  <link href="https://blogger.example/"/>
  <entry>
    <id>post-1</id><title>Post</title>
    <updated>2026-07-12T10:00:00Z</updated>
    <published>2026-07-12T10:00:00Z</published>
    <author><name>Alice</name><email>alice@example.test</email>
      <uri>https://alice.example/</uri></author>
    <content type="html">&lt;p&gt;Post body&lt;/p&gt;</content>
    <category scheme="http://schemas.google.com/g/2005#kind"
      term="http://schemas.google.com/blogger/2008/kind#post"/>
    <category scheme="http://www.blogger.com/atom/ns#" term="Python"/>
  </entry>
  <entry>
    <id>comment-1</id><title>Comment</title>
    <updated>2026-07-12T11:00:00Z</updated>
    <author><name>Visitor</name><uri>https://visitor.example/</uri></author>
    <content type="html">&lt;p&gt;Nice post&lt;/p&gt;</content>
    <category scheme="http://schemas.google.com/g/2005#kind"
      term="http://schemas.google.com/blogger/2008/kind#comment"/>
    <thr:in-reply-to ref="post-1"/>
  </entry>
</feed>"""
imported_blog = parse_feed(BytesIO(blogger))
assert len(imported_blog.posts) == 1
assert imported_blog.posts[0].tags[0].name == "Python"
assert len(imported_blog.posts[0].comments) == 1
assert "Nice post" in imported_blog.posts[0].comments[0].body

# The sample request-class plugin creates remote users and handles explicit app
# construction correctly.
response = client.get("/", environ_overrides={"REMOTE_USER": "remote-user"})
assert response.status_code == 200
from zine.models import User
assert User.query.filter_by(username="remote-user").one().email == (
    "remote-user@example.com"
)

# Discovery reflects disabled configuration without importing or setting up
# plugins again.
from zine.pluginsystem import find_plugins
app.cfg.change_single("plugins", ["vessel_theme"])
discovered = {plugin.name: plugin.active for plugin in find_plugins(app)}
assert discovered["vessel_theme"] is True
assert all(
    not active for name, active in discovered.items()
    if name != "vessel_theme"
)
'''


def test_all_bundled_plugins_and_themes(tmp_path):
    instance = tmp_path / "instance"
    instance.mkdir()
    env = os.environ.copy()
    env["ZINE_TEST_INSTANCE"] = str(instance)
    env["ZINE_TEST_PLUGINS"] = ",".join(PLUGIN_NAMES)
    result = subprocess.run(
        [sys.executable, "-c", PLUGIN_SCRIPT],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
