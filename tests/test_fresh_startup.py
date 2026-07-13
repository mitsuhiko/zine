import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from werkzeug.test import Client
from werkzeug.wrappers import Response

from zine.websetup import WebSetup


ROOT = Path(__file__).resolve().parents[1]


SETUP_SCRIPT = r"""
import os
from pathlib import Path

from werkzeug.test import Client
from werkzeug.wrappers import Response

from zine import _core, get_wsgi_app

instance = Path(os.environ["ZINE_TEST_INSTANCE"])
client = Client(get_wsgi_app(str(instance)), Response)

setup_page = client.get("/")
assert setup_page.status_code == 200
assert b"Welcome To The Zine Setup" in setup_page.data

finished = client.post("/", data={
    "_startsetup": "1",
    "_lang": "en",
    "database_uri": "sqlite://zine.db",
    "admin_username": "admin",
    "admin_email": "admin@example.test",
    "admin_password": "secret",
    "admin_password2": "secret",
})
assert finished.status_code == 200
assert b"Setup Finished" in finished.data
assert (instance / "zine.ini").is_file()
assert (instance / "zine.db").is_file()

index = client.get("/")
assert index.status_code == 200
assert b"Index &mdash; My Zine Blog" in index.data

application = _core._application
assert application.initialized
assert application.theme.name == "vessel"
assert application.plugins["vessel_theme"].active
assert application.plugins["vessel_theme"].setup_error is None
metadata = dict(application.plugins["vessel_theme"].metadata.iteritems())
assert metadata["name"] == "Vessel Theme"
assert application.url_adapter.build("blog/index") == "/"
assert application.url_adapter.build("admin/index") == "/admin/"
from zine.database import validate_database
validate_database(application.database_engine)

from zine.models import User
administrator = User.query.filter_by(username="admin").one()
assert administrator.email == "admin@example.test"
assert administrator.check_password("secret")
assert administrator.is_admin

stylesheet = client.get("/_shared/vessel_theme/style.css")
assert stylesheet.status_code == 200
assert b"body" in stylesheet.data
"""


def _run_setup(instance):
    env = os.environ.copy()
    env["ZINE_TEST_INSTANCE"] = str(instance)
    result = subprocess.run(
        [sys.executable, "-c", SETUP_SCRIPT],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_fresh_setup_startup_and_development_server(tmp_path):
    instance = tmp_path / "instance"
    instance.mkdir()
    _run_setup(instance)

    port = _free_port()
    server = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "scripts/server"),
            "--no-reloader",
            "--no-debugger",
            "--hostname", "127.0.0.1",
            "--port", str(port),
            "--instance", str(instance),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        url = "http://127.0.0.1:%d/" % port
        deadline = time.monotonic() + 15
        while True:
            if server.poll() is not None:
                output = server.stdout.read()
                raise AssertionError("development server exited:\n" + output)
            try:
                with urlopen(url, timeout=1) as response:
                    body = response.read()
                    assert response.status == 200
                    assert b"Index &mdash; My Zine Blog" in body
                    break
            except URLError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


def test_failed_database_setup_does_not_hide_wizard(tmp_path):
    instance = tmp_path / "instance"
    instance.mkdir()
    client = Client(WebSetup(str(instance)), Response)

    response = client.post("/", data={
        "_startsetup": "1",
        "_lang": "en",
        "database_uri": "unknown-database://localhost/zine",
        "admin_username": "admin",
        "admin_email": "admin@example.test",
        "admin_password": "secret",
        "admin_password2": "secret",
    })

    assert response.status_code == 200
    assert b"Error" in response.data
    assert not (instance / "zine.ini").exists()
    assert b"Could not parse SQLAlchemy URL" in response.data
