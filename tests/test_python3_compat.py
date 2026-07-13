import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = ("zine", "tests", "api", "external-plugins")
TOOL_ROOTS = ("scripts", "servers")


def _maintained_python_sources():
    sources = [
        source
        for source_root in SOURCE_ROOTS
        for source in (ROOT / source_root).rglob("*.py")
    ]
    sources.extend(
        source
        for tool_root in TOOL_ROOTS
        for source in (ROOT / tool_root).iterdir()
        if source.is_file()
        and (
            source.suffix in {".py", ".cgi", ".fcgi", ".wsgi"}
            or source.read_bytes().startswith(
                (b"#!/usr/bin/env python", b"#!/usr/bin/python")
            )
        )
    )
    return sorted(sources)


@pytest.mark.parametrize(
    "source",
    _maintained_python_sources(),
    ids=lambda source: str(source.relative_to(ROOT)),
)
def test_source_compiles(source):
    compile(source.read_bytes(), str(source), "exec")


def test_core_modules_import_without_compatibility_warnings():
    modules = []
    for source in (ROOT / "zine").rglob("*.py"):
        module = ".".join(source.with_suffix("").relative_to(ROOT).parts)
        if module.startswith("zine.plugins."):
            continue
        if module.endswith(".__init__"):
            module = module[:-9]
        modules.append(module)

    code = "\n".join(
        ["import importlib"]
        + ["importlib.import_module(%r)" % module
           for module in sorted(set(modules))]
    )
    env = os.environ.copy()
    env["PYTHONWARNINGS"] = "error"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)


def test_naive_utc_helpers_use_modern_datetime_apis():
    from datetime import datetime, timezone

    from zine.utils.dates import utcfromtimestamp, utcnow

    current = utcnow()
    assert current.tzinfo is None
    expected = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((expected - current).total_seconds()) < 5
    assert utcfromtimestamp(0) == datetime(1970, 1, 1)


def test_python2_compatibility_aliases_are_gone():
    from zine.config import Configuration
    from zine.database import db
    from zine.pluginsystem import MetaData
    from zine.utils.datastructures import OrderedDict, ReadOnlyMultiMapping

    for type_ in (Configuration, MetaData, OrderedDict, ReadOnlyMultiMapping):
        assert not hasattr(type_, "iteritems")
        assert not hasattr(type_, "iterkeys")
        assert not hasattr(type_, "itervalues")
    assert not hasattr(db, "save")
    assert not hasattr(db, "clear")
    assert not hasattr(db, "basic_mapper")
