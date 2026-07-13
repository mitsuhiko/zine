import tomllib
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, Table, inspect, text

from zine import database


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CORE_TABLES = {
    "categories",
    "comments",
    "group_privileges",
    "group_users",
    "groups",
    "notification_subscriptions",
    "post_categories",
    "post_links",
    "post_tags",
    "posts",
    "privileges",
    "redirects",
    "tags",
    "texts",
    "user_privileges",
    "users",
}


def test_fresh_schema_is_deterministic_and_current():
    engine = database.create_engine("sqlite:memory")
    plugin_table = Table(
        "test_unrelated_plugin_table",
        database.metadata,
        Column("id", Integer, primary_key=True),
    )
    try:
        database.init_database(engine)
        database.init_database(engine)
        database.validate_database(engine)

        assert set(inspect(engine).get_table_names()) == EXPECTED_CORE_TABLES
        assert "schema_versions" not in inspect(engine).get_table_names()
    finally:
        database.metadata.remove(plugin_table)
        engine.dispose()


def test_schema_validation_rejects_missing_tables():
    engine = database.create_engine("sqlite:memory")
    try:
        database.init_database(engine)
        database.comments.drop(engine)

        with pytest.raises(database.DatabaseSchemaError) as error:
            database.validate_database(engine)
        assert "missing tables: comments" in str(error.value)
        assert "create a fresh instance" in str(error.value)
    finally:
        engine.dispose()


def test_schema_validation_rejects_mismatched_columns():
    engine = database.create_engine("sqlite:memory")
    try:
        tables = [
            table for table in database.CORE_TABLES
            if table is not database.users
        ]
        database.metadata.create_all(engine, tables=tables)
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE users (user_id INTEGER PRIMARY KEY)"
            ))

        with pytest.raises(database.DatabaseSchemaError) as error:
            database.validate_database(engine)
        assert "users columns differ" in str(error.value)
    finally:
        engine.dispose()


def test_legacy_migration_dependency_and_package_are_removed():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    dependencies = project["project"]["dependencies"]

    assert not any("sqlalchemy-migrate" in item for item in dependencies)
    assert "sqlalchemy-migrate" not in (ROOT / "uv.lock").read_text()
    assert not (ROOT / "zine/upgrades").exists()
    assert not (ROOT / "scripts/manage-database").exists()
