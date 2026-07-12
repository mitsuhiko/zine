from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = ("zine", "tests", "api", "external-plugins")


def _maintained_python_sources():
    sources = [
        source
        for source_root in SOURCE_ROOTS
        for source in (ROOT / source_root).rglob("*.py")
    ]
    sources.extend(
        source
        for source in (ROOT / "scripts").iterdir()
        if source.is_file()
        and (
            source.suffix == ".py"
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
