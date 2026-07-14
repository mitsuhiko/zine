import importlib.util
import os
import pickle
import runpy
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from contextlib import closing
from pathlib import Path
from zipfile import ZipFile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run_script(name, *args, input=None, timeout=90):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *map(str, args)],
        cwd=ROOT,
        input=input,
        capture_output=True,
        text=True,
        check=True,
        timeout=timeout,
    )


def test_instance_command_line_tools(tmp_path):
    instance = tmp_path / "instance"
    result = run_script(
        "reset-instance",
        instance,
        "--username",
        "admin",
        "--password",
        "secret",
    )
    assert "All done." in result.stdout
    assert (instance / "zine.ini").is_file()
    with closing(sqlite3.connect(instance / "zine.db")) as connection:
        assert connection.execute(
            "select username from users"
        ).fetchone() == ("admin",)

    server_help = run_script("server", "--help")
    assert "--no-reloader" in server_help.stdout
    test_help = run_script("run-tests", "--help")
    assert "pytest" in test_help.stdout.lower()

    aliases = run_script("create-apache-config", "-I", instance)
    assert "Alias /_shared/core" in aliases.stdout
    regenerated = run_script("regenerate-post-uids", "-I", instance)
    assert "Done regenerating post uids." in regenerated.stdout
    shell = run_script(
        "shell", "--no-ipython", "-I", instance, input="exit()\n"
    )
    assert "Zine Shell" in shell.stdout + shell.stderr
    event_map = run_script("build-event-map", "-I", instance)
    assert "Events emitted" in event_map.stdout
    assert "before-render-template" in event_map.stdout


def test_plugin_creation_and_bundling_tools(tmp_path):
    wizard_input = "My Plugin\n\nExample Author\nhttps://example.test\n\n"
    run_script("new-plugin", tmp_path, input=wizard_input)
    generated = tmp_path / "my_plugin"
    assert (generated / "metadata.txt").is_file()
    compile(
        (generated / "__init__.py").read_text(),
        str(generated / "__init__.py"),
        "exec",
    )

    instance = tmp_path / "instance"
    run_script("reset-instance", instance)
    plugin_folder = instance / "plugins" / "dark_vessel_colorscheme"
    shutil.copytree(
        ROOT / "external-plugins" / "dark_vessel_colorscheme", plugin_folder
    )
    package = tmp_path / "dark.plugin"
    bundled = run_script(
        "bundle-plugin", "-I", instance, "dark_vessel_colorscheme", package
    )
    assert "Plugin written" in bundled.stdout
    with ZipFile(package) as archive:
        assert archive.read("ZINE_PLUGIN") == b"dark_vessel_colorscheme"
        assert "pdata/shared/dark.css" in archive.namelist()

    translit = runpy.run_path(str(SCRIPTS / "generate-translit-tab"))
    target = tmp_path / "translit_tab.py"
    target.write_text('"""Generated table."""\nOLD = True\n')
    translit["update_mapping"](
        {228: "ae"}, {228: "a"}, {228: "a"}, str(target)
    )
    generated_source = target.read_text()
    assert "LONG_TABLE" in generated_source
    assert "228: 'ae'" in generated_source
    compile(generated_source, str(target), "exec")


def test_translation_command_line_tools(tmp_path):
    from zine.i18n import load_core_translations

    translations = load_core_translations("de")
    assert translations.gettext("Save") == "Speichern"
    assert translations.client_keys

    plugin = tmp_path / "translation_plugin"
    plugin.mkdir()
    (plugin / "__init__.py").write_text(
        "from zine.i18n import _\n_(\"Command line translation\")\n"
    )

    extracted = run_script("extract-messages", plugin)
    assert "All done." in extracted.stdout
    pot = plugin / "i18n" / "messages.pot"
    assert b"Command line translation" in pot.read_bytes()

    run_script("add-translation", "--plugin", plugin, "fr")
    updated = run_script("update-translations", plugin, "--statistics")
    assert "Updating 'fr'" in updated.stdout
    compiled = run_script("compile-translations", plugin, "--statistics")
    assert "Compiling 'fr'" in compiled.stdout
    assert (plugin / "i18n" / "fr" / "messages.mo").is_file()


def test_user_and_api_documentation_builds(tmp_path):
    from zine.docs import load_page

    class DocumentationApp:
        cfg = {"language": "en"}
        plugins = {}

    source_page, is_index = load_page(DocumentationApp(), "")
    assert is_index is True
    assert source_page["title"] == "Zine Help"

    from zine.pluginsystem import Plugin

    plugin_app = DocumentationApp()
    plugin_app.plugin_folder = str(tmp_path / "plugins")
    documented = Plugin(
        plugin_app,
        "eric_the_fish",
        str(ROOT / "external-plugins" / "eric_the_fish"),
        False,
    )
    assert documented.is_documented is True

    project = tmp_path / "plugin"
    shutil.copytree(ROOT / "zine" / "docs", project / "docs")
    built = run_script("build-documentation", project)
    assert "All done." in built.stdout
    page_file = project / "docs" / "en" / "index.page"
    with page_file.open("rb") as fileobj:
        page = pickle.load(fileobj)
    assert page["title"] == "Zine Help"
    assert "Welcome to the Zine help" in page["body"]

    pytest.importorskip("sphinx")
    for builder, expected in (("html", "index.html"),
                              ("webpickle", "index.fpickle")):
        output = tmp_path / builder
        doctrees = tmp_path / (builder + "-doctrees")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "sphinx",
                "-W",
                "-b",
                builder,
                "-d",
                str(doctrees),
                str(ROOT / "api"),
                str(output),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=90,
        )
        assert (output / expected).is_file()


def test_deployment_runner_templates_import(tmp_path, monkeypatch):
    from zine.database import db

    monkeypatch.setenv("ZINE_POOL_SIZE", "2")
    engine = db.create_engine("sqlite://pool.db", str(tmp_path))
    assert engine.pool.size() == 2
    engine.dispose()

    instance = tmp_path / "instance"
    env = os.environ.copy()
    env["ZINE_INSTANCE"] = str(instance)
    for runner in ("zine.wsgi", "zine.cgi", "zine.fcgi"):
        if runner.endswith(".fcgi") and importlib.util.find_spec("flup") is None:
            continue
        code = (
            "import runpy; data = runpy.run_path(%r); "
            "assert callable(data['application'])" % str(ROOT / "servers" / runner)
        )
        subprocess.run(
            [sys.executable, "-c", code],
            cwd=tmp_path,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    assert "flup" not in (ROOT / "servers" / "zine.wsgi").read_text()


def test_standard_source_and_wheel_packages(tmp_path):
    pytest.importorskip("build")
    destination = tmp_path / "dist"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--outdir",
            str(destination),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    wheel = next(destination.glob("*.whl"))
    source = next(destination.glob("*.tar.gz"))
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "zine/cli.py" in names
        entry_points = archive.read(next(
            name for name in names if name.endswith("entry_points.txt")
        ))
        assert b"zine-server = zine.cli:server_main" in entry_points
        metadata = archive.read(next(
            name for name in names if name.endswith("METADATA")
        ))
        assert b"Description-Content-Type: text/markdown" in metadata
        assert b"revival of the historical Zine 0.2" in metadata
        assert "zine/templates/index.html" in names
    with tarfile.open(source) as archive:
        names = archive.getnames()
        assert any(name.endswith("README.md") for name in names)
        assert any(name.endswith("README_OLD.txt") for name in names)
        assert any(name.endswith("scripts/server") for name in names)
        assert any(name.endswith("servers/zine.wsgi") for name in names)
        assert any(
            name.endswith("external-plugins/eric_the_fish/__init__.py")
            for name in names
        )
