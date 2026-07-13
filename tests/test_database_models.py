from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect, select
from werkzeug.exceptions import NotFound

from zine import database
from zine import models, privileges
from zine.utils import redirects


@pytest.fixture
def sqlite_database(monkeypatch, tmp_path):
    database.session.remove()
    engine = database.create_engine("sqlite://zine.db", relative_to=tmp_path)
    database.init_database(engine)
    monkeypatch.setattr(database, "get_engine", lambda: engine)

    def parse_single(self, text):
        self.parser_data["body"] = None

    def parse_dual(self, text):
        self.parser_data.update(intro=None, body=None)

    monkeypatch.setattr(models._ZEMLContainer, "_parse_text", parse_single)
    monkeypatch.setattr(models._ZEMLDualContainer, "_parse_text", parse_dual)
    app = SimpleNamespace(
        privileges={models.BLOG_ADMIN.name: models.BLOG_ADMIN}
    )
    monkeypatch.setattr(models, "get_application", lambda: app)
    monkeypatch.setattr(privileges, "get_application", lambda: app)

    try:
        yield engine
    finally:
        database.session.rollback()
        database.session.remove()
        engine.dispose()


def _post(title, author, pub_date):
    slug = title.lower().replace(" ", "-")
    return models.Post(
        title,
        author,
        "%s body" % title,
        slug=slug,
        uid="tag:example.test,2026:%s" % slug,
        pub_date=pub_date,
        parser="test",
    )


def test_fresh_sqlite_crud_and_relationships(sqlite_database):
    now = datetime.now()
    user = models.User(
        "alice", "secret", "alice@example.test", is_author=True
    )
    group = models.Group("editors")
    group.users.append(user)
    user.own_privileges.add(models.BLOG_ADMIN)
    category = models.Category("News", slug="news")
    tag = models.Tag("Python", slug="python")
    older = _post("Older", user, now - timedelta(days=1))
    newer = _post("Newer", user, now)
    older.categories.append(category)
    older.tags.append(tag)
    older.links.append(
        models.PostLink(older, "https://example.test/episode.mp3")
    )

    approved = models.Comment(
        older,
        "Visitor",
        "A useful comment",
        email="visitor@example.test",
        parser="test",
    )
    blocked = models.Comment(
        older,
        "Spammer",
        "Spam",
        email="spam@example.test",
        parser="test",
        status=models.COMMENT_BLOCKED_SPAM,
    )

    assert inspect(user).session is database.session()
    assert older.comment_count == 1
    blocked.status = models.COMMENT_MODERATED
    assert older.comment_count == 2
    blocked.status = models.COMMENT_BLOCKED_SPAM
    assert older.comment_count == 1

    database.session.commit()
    user_id = user.id
    group_id = group.id
    tag_id = tag.id
    older_id = older.id
    approved_id = approved.id
    database.session.remove()

    loaded_user = models.User.query.get(user_id)
    loaded_post = models.Post.query.get(older_id)
    assert loaded_user.username == "alice"
    assert loaded_user.check_password("secret")
    assert loaded_user.is_admin
    assert [post.title for post in loaded_user.posts.all()] == [
        "Newer", "Older"
    ]
    loaded_group = models.Group.query.get(group_id)
    assert loaded_group.users.filter_by(username="alice").one() == loaded_user
    assert loaded_post.author == loaded_user
    assert loaded_post.text == "Older body"
    assert [item.name for item in loaded_post.categories] == ["News"]
    assert [item.name for item in loaded_post.tags] == ["Python"]
    assert loaded_post.links[0].href.endswith("episode.mp3")
    assert loaded_post.comment_count == 1
    assert models.Post.query.all()[0].title == "Newer"
    assert models.Post.query.search("Older") == [loaded_post]

    database.session.remove()
    lightweight = models.Post.query.lightweight(
        lazy=("comments",)
    ).get(older_id)
    assert not database.attribute_loaded(lightweight, "comments")
    assert lightweight.comment_count == 1
    assert models.Comment.query.post_lightweight().get(approved_id).post.id == older_id

    summary = models.SummarizedPost.query.get(older_id)
    assert summary.title == "Older"
    assert summary.comment_count == 1

    cloud = models.Tag.query.get_cloud()
    assert cloud == [{
        "id": tag_id,
        "slug": "python",
        "name": "Python",
        "count": 1,
        "size": 100.0,
    }]

    lightweight.comments.remove(models.Comment.query.get(approved_id))
    assert lightweight.comment_count == 0
    database.session.commit()
    assert models.Comment.query.get(approved_id) is None


def test_query_helpers_and_declarative_plugin_model(sqlite_database):
    class Widget(database.db.Model):
        __tablename__ = "test_widgets"

        id = database.db.Column(database.db.Integer, primary_key=True)
        name = database.db.Column(database.db.String(40), nullable=False)

    database.metadata.create_all(sqlite_database)
    widget = Widget(name="example")
    assert widget in database.session.new
    database.session.commit()

    assert Widget.query.get(widget.id).name == "example"
    assert Widget.query.filter_by(name="missing").first() is None
    with pytest.raises(NotFound):
        Widget.query.filter_by(name="missing").first(raise_if_missing=True)


def test_modern_core_statements_for_redirects(sqlite_database, monkeypatch):
    monkeypatch.setattr(
        redirects,
        "get_application",
        lambda: SimpleNamespace(cfg={"blog_url": "https://example.test/"}),
    )
    monkeypatch.setattr(
        redirects,
        "make_external_url",
        lambda value: "https://example.test/" + value,
    )

    redirects.register_redirect("old", "new")
    assert redirects.lookup_redirect("old") == "https://example.test/new"
    assert redirects.get_redirect_map() == {
        "old": "https://example.test/new"
    }
    redirects.unregister_redirect("old")
    with pytest.raises(ValueError):
        redirects.unregister_redirect("old")


def test_engine_urls_and_debug_events(monkeypatch, tmp_path):
    relative = database.create_engine(
        "sqlite://nested.db?timeout=5", relative_to=tmp_path
    )
    try:
        assert relative.url.database == str(tmp_path / "nested.db")
        assert relative.url.query["timeout"] == "5"
    finally:
        relative.dispose()

    assert database.secure_database_uri(
        "postgresql://user:secret@localhost/zine"
    ) == "postgresql://user:***@localhost/zine"

    request = SimpleNamespace(queries=[])
    import zine.application
    monkeypatch.setattr(zine.application, "get_request", lambda: request)
    engine = database.create_engine("sqlite:memory", debug=True)
    try:
        with engine.connect() as connection:
            assert connection.execute(select(1)).scalar_one() == 1
    finally:
        engine.dispose()

    assert len(request.queries) == 1
    statement, parameters, started, finished, calling_context = request.queries[0]
    assert "SELECT" in statement
    assert started <= finished
    assert calling_context is not None


def test_database_mappers_use_sqlalchemy_2_registry():
    assert inspect(models.User).persist_selectable is database.users
    assert inspect(models.Post).primary_key == (database.posts.c.post_id,)
    assert inspect(models.Comment).primary_key == (database.comments.c.comment_id,)
