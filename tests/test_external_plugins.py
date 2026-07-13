import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_PLUGINS = [
    "dark_vessel_colorscheme",
    "eric_the_fish",
    "markdown_parser",
]


EXTERNAL_PLUGIN_SCRIPT = r'''
import json
import os
import re
from pathlib import Path

from werkzeug.test import Client
from werkzeug.wrappers import Response

from zine import _core, get_wsgi_app

root = Path(os.environ["ZINE_TEST_ROOT"])
instance = Path(os.environ["ZINE_TEST_INSTANCE"])
external_plugins = os.environ["ZINE_TEST_PLUGINS"].split(",")
plugin_folder = instance / "plugins"
plugin_folder.mkdir()
for name in external_plugins:
    (plugin_folder / name).symlink_to(
        root / "external-plugins" / name, target_is_directory=True
    )

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
config.write_text(config.read_text().replace(
    "plugins = vessel_theme",
    "plugins = vessel_theme, " + ", ".join(external_plugins),
))

index = client.get("/")
assert index.status_code == 200
app = _core._application
for name in external_plugins:
    plugin = app.plugins[name]
    assert plugin.active
    assert plugin.setup_error is None
    assert plugin.module is not None

# The colorscheme augments Vessel and exports its own static asset.
vessel = app.plugins["vessel_theme"].module
assert "dark_vessel_colorscheme::dark.css" in vessel.variations
dark_css = client.get("/_shared/dark_vessel_colorscheme/dark.css")
assert dark_css.status_code == 200
assert b"background" in dark_css.data

# Eric creates and seeds its own fresh-instance table without migrations.
from zine.plugins.eric_the_fish.database import Fortune, initialize
from zine.plugins.eric_the_fish.fortunes import FORTUNES
assert Fortune.query.count() == len(FORTUNES)
initialize(app.database_engine)
assert Fortune.query.count() == len(FORTUNES)
fortune = client.get("/_services/json/eric_the_fish/get_fortune")
assert fortune.status_code == 200
assert json.loads(fortune.get_data(as_text=True))["fortune"] in FORTUNES
fish_js = client.get("/_shared/eric_the_fish/fish.js")
assert fish_js.status_code == 200

# Log in through the real CSRF-protected form and render plugin configuration.
login = client.get("/account/login")
token = re.search(
    rb'name="_csrf_token" value="([^"]+)', login.data
).group(1).decode("ascii")
logged_in = client.post("/account/login", data={
    "user": "admin",
    "password": "secret",
    "permanent": "",
    "_csrf_token": token,
})
assert logged_in.status_code == 302
for url, marker in (
    ("/admin/options/eric-the-fish", b"Eric The Fish"),
    ("/admin/options/markdown", b"Markdown Parser"),
    ("/admin/options/theme/configure", b"Dark"),
):
    response = client.get(url)
    assert response.status_code == 200, url
    assert marker in response.data, url
    assert b"&lt;form" not in response.data, url
assert b"$ERIC_THE_FISH_SKIN" in client.get(
    "/admin/options/eric-the-fish"
).data

# Modern Python-Markdown output, intro splitting, extensions, and comment
# sanitization preserve the external parser's behavior.
from zine.parsers import parse
rendered = parse("# Heading\n\n**bold**", "markdown", "post").to_html()
assert "<h1>Heading</h1>" in rendered
assert "<strong>bold</strong>" in rendered
comment = parse(
    "Text\n\n<script>alert('bad')</script>", "markdown", "comment"
).to_html()
assert "<script" not in comment

markdown = app.plugins["markdown_parser"].module
app.cfg.change_single(markdown.CFG_MAKEINTRO, True)
intro = parse(
    "Intro\n\n<!--more-->\n\nBody", "markdown", "post"
).to_html()
assert "<intro>" in intro and "Body" in intro
app.cfg.change_single(
    markdown.CFG_EXTENSIONS, ["fenced_code", "codehilite"]
)
code = parse("```python\nprint('hello')\n```", "markdown", "post").to_html()
assert "syntax" in code and "print" in code

# Discovery tracks disabled external plugins without any old migration hooks.
from zine.pluginsystem import find_plugins
app.cfg.change_single("plugins", ["vessel_theme"])
discovered = {plugin.name: plugin.active for plugin in find_plugins(app)}
assert discovered["vessel_theme"] is True
for name in external_plugins:
    assert discovered[name] is False
'''


def test_external_example_plugins(tmp_path):
    instance = tmp_path / "instance"
    instance.mkdir()
    env = os.environ.copy()
    env["ZINE_TEST_ROOT"] = str(ROOT)
    env["ZINE_TEST_INSTANCE"] = str(instance)
    env["ZINE_TEST_PLUGINS"] = ",".join(EXTERNAL_PLUGINS)
    result = subprocess.run(
        [sys.executable, "-c", EXTERNAL_PLUGIN_SCRIPT],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
