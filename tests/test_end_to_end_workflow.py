import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


WORKFLOW_SCRIPT = r'''
import os
import re
from pathlib import Path
from xml.etree import ElementTree

from werkzeug.test import Client
from werkzeug.wrappers import Response

from zine import _core, get_wsgi_app


instance = Path(os.environ["ZINE_TEST_INSTANCE"])
client = Client(get_wsgi_app(str(instance)), Response)


def csrf(path):
    response = client.get(path)
    assert response.status_code == 200, (path, response.status_code)
    match = re.search(rb'name="_csrf_token" value="([^"]+)', response.data)
    assert match is not None, path
    return match.group(1).decode("ascii")


def post_form(path, data):
    data = dict(data)
    data["_csrf_token"] = csrf(path)
    return client.post(path, data=data)


def login():
    response = post_form("/account/login", {
        "user": "admin",
        "password": "secret",
        "permanent": "False",
    })
    assert response.status_code == 302
    assert response.location == "/admin/"


# Install a completely fresh instance through the public setup application.
setup = client.get("/")
assert setup.status_code == 200
assert b"Welcome To The Zine Setup" in setup.data
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
assert client.get("/").status_code == 200
login()

# Persist configuration through the admin form and exercise an in-process
# application reload. The session and bundled plugin remain usable afterwards.
configured = post_form("/admin/options/basic", {
    "blog_title": "Ported Zine",
    "blog_tagline": "Python 3 Blog",
    "blog_email": "admin@example.test",
    "language": "en",
    "timezone": "UTC",
    "session_cookie_name": "zine_session",
    "comments_enabled": "True",
    "moderate_comments": "0",
    "comments_open_for": "0",
    "pings_enabled": "True",
    "use_flat_comments": "False",
    "default_parser": "zeml",
    "comment_parser": "text",
    "posts_per_page": "10",
})
assert configured.status_code == 302
reloaded = client.get(configured.location)
assert reloaded.status_code == 302
reloaded = client.get(reloaded.location)
assert reloaded.status_code == 200
application = _core._application
assert application.cfg["blog_title"] == "Ported Zine"
assert application.cfg["moderate_comments"] == 0
assert application.plugins["vessel_theme"].active
assert application.plugins["vessel_theme"].setup_error is None

# Database errors must reach Werkzeug's debugger in development mode instead
# of being converted into a blank internal-error page.
from sqlalchemy.exc import SQLAlchemyError

original_entries_view = application.views["admin/manage_entries"]


def fail_with_database_error(request, page):
    raise SQLAlchemyError("debug database failure")


application.views["admin/manage_entries"] = fail_with_database_error
try:
    try:
        client.get("/admin/entries/")
    except SQLAlchemyError as error:
        assert "debug database failure" in str(error)
    else:
        raise AssertionError("database error did not pass through")
finally:
    application.views["admin/manage_entries"] = original_entries_view

config_text = (instance / "zine.ini").read_text()
assert "blog_title" in config_text and "Ported Zine" in config_text
assert b"Ported Zine" in client.get("/").data

# Render every ID-independent administration page. This catches Python 2
# ordering assumptions and other compatibility failures in less-used views.
for admin_path in (
    "/admin/",
    "/admin/entries/",
    "/admin/entries/new",
    "/admin/pages/",
    "/admin/pages/new",
    "/admin/comments/",
    "/admin/comments/unmoderated",
    "/admin/comments/approved",
    "/admin/comments/blocked",
    "/admin/comments/spam",
    "/admin/categories/",
    "/admin/categories/new",
    "/admin/users/",
    "/admin/users/new",
    "/admin/groups/",
    "/admin/groups/new",
    "/admin/options/basic",
    "/admin/options/urls",
    "/admin/options/theme/",
    "/admin/options/theme/configure",
    "/admin/options/cache",
    "/admin/options/configuration",
    "/admin/system/",
    "/admin/system/maintenance",
    "/admin/system/log",
    "/admin/system/import/",
    "/admin/system/export",
    "/admin/system/plugins/",
    "/admin/system/help/",
):
    response = client.get(admin_path)
    assert response.status_code == 200, (admin_path, response.status_code)

for account_path in (
    "/account/",
    "/account/profile",
    "/account/notifications",
    "/account/system/about",
    "/account/system/help/",
):
    response = client.get(account_path)
    assert response.status_code == 200, (account_path, response.status_code)

from zine.database import db
from zine.models import Category, Comment, Post, Tag

# Category create and update through its admin views.
created = post_form("/admin/categories/new", {
    "slug": "news",
    "name": "News",
    "description": "Fresh install news",
})
assert created.status_code == 302
category = Category.query.filter_by(slug="news").one()
updated = post_form("/admin/categories/%d" % category.id, {
    "slug": "news",
    "name": "Porting News",
    "description": "Updated category",
})
assert updated.status_code == 302
assert Category.query.filter_by(slug="news").one().name == "Porting News"

# Entry create/read/update, including category and tag binding.
entry_data = {
    "title": "Hello Python",
    "text": "<p>First body</p>",
    "status": "2",
    "pub_date": "",
    "slug": "hello-python",
    "author": "admin",
    "tags": "Python, Porting",
    "categories": str(category.id),
    "parser": "html",
    "comments_enabled": "True",
    "pings_enabled": "True",
    "ping_links": "False",
}
created = post_form("/admin/entries/new", entry_data)
assert created.status_code == 302
entry = Post.query.filter_by(slug="hello-python").one()
assert entry.content_type == "entry"
assert {tag.name for tag in entry.tags} == {"Python", "Porting"}
assert [item.name for item in entry.categories] == ["Porting News"]
managed_entries = client.get("/admin/entries/")
assert managed_entries.status_code == 200
assert b"Hello Python" in managed_entries.data
public_entry = client.get("/hello-python")
assert public_entry.status_code == 200
assert b"First body" in public_entry.data

entry_data.update({
    "title": "Hello Python 3",
    "text": "<p>Updated body</p>",
    "tags": "Python Modern",
})
updated = post_form("/admin/p/%d" % entry.id, entry_data)
assert updated.status_code == 302
entry = Post.query.filter_by(slug="hello-python").one()
assert entry.title == "Hello Python 3"
assert [tag.name for tag in entry.tags] == ["Python Modern"]
assert b"Updated body" in client.get("/hello-python").data
assert client.get("/categories/news").status_code == 200
assert client.get("/tags/python-modern").status_code == 200
for public_path in (
    "/", "/archive", "/authors/", "/authors/admin", "/tags/", "/_services/"
):
    assert client.get(public_path).status_code == 200, public_path

# Pages use the same CRUD pipeline but retain their distinct content type.
page_data = {
    "title": "About",
    "text": "<p>About this port</p>",
    "status": "2",
    "pub_date": "",
    "slug": "about",
    "author": "admin",
    "tags": "",
    "parser": "html",
    "comments_enabled": "False",
    "pings_enabled": "False",
    "ping_links": "False",
}
created = post_form("/admin/pages/new", page_data)
assert created.status_code == 302
page = Post.query.filter_by(slug="about").one()
assert page.content_type == "page"
assert b"About this port" in client.get("/about").data
page_data.update({"title": "About Zine", "text": "<p>Updated page</p>"})
updated = post_form("/admin/p/%d" % page.id, page_data)
assert updated.status_code == 302
assert b"Updated page" in client.get("/about").data

# Anonymous comment creation followed by authenticated edit and deletion.
logout = client.get("/account/logout")
assert logout.status_code == 302
commented = post_form("/hello-python", {
    "author": "Reader",
    "email": "reader@example.test",
    "www": "",
    "body": "A useful comment",
    "parent": "",
})
assert commented.status_code == 302
comment = Comment.query.one()
assert comment.author == "Reader"
assert comment.blocked is False
assert b"A useful comment" in client.get("/hello-python").data

login()
changed = post_form("/admin/comments/%d" % comment.id, {
    "author": "Reader Updated",
    "email": "reader@example.test",
    "www": "",
    "text": "An edited comment",
    "pub_date": "2026-07-13 12:00",
    "parser": "text",
    "blocked": "False",
    "blocked_msg": "",
})
assert changed.status_code == 302
comment = Comment.query.one()
assert comment.author == "Reader Updated"
assert comment.text == "An edited comment"
assert b"An edited comment" in client.get("/hello-python").data

# Main feeds are valid XML and contain the published entry, not the page.
for feed_url, root_name in (("/feed.atom", "feed"), ("/feed/rss2", "rss")):
    response = client.get(feed_url)
    assert response.status_code == 200
    root = ElementTree.fromstring(response.data)
    assert root.tag.rsplit("}", 1)[-1] == root_name
    assert b"Hello Python 3" in response.data
    assert b"About Zine" not in response.data

removed_comment = post_form(
    "/admin/comments/%d/delete" % comment.id, {"confirm": "True"}
)
assert removed_comment.status_code == 302
assert Comment.query.count() == 0

# Delete both post types and the category through the real admin dialogs.
removed_page = post_form(
    "/admin/p/%d/delete" % page.id, {"confirm": "True"}
)
assert removed_page.status_code == 302
assert client.get("/about").status_code == 404
removed_entry = post_form(
    "/admin/p/%d/delete" % entry.id, {"confirm": "True"}
)
assert removed_entry.status_code == 302
assert client.get("/hello-python").status_code == 404
removed_category = post_form(
    "/admin/categories/%d/delete" % category.id, {"confirm": "True"}
)
assert removed_category.status_code == 302
assert client.get("/categories/news").status_code == 404

# Tags are created by post forms. Once detached, their model records can be
# updated and deleted without stale relationships.
tag = Tag.query.filter_by(slug="python-modern").one()
tag.name = "Python Current"
tag.slug = "python-current"
db.commit()
assert client.get("/tags/python-current").status_code == 200
db.delete(tag)
db.commit()
assert client.get("/tags/python-current").status_code == 404
assert Post.query.count() == 0
'''


def test_complete_fresh_instance_workflow(tmp_path):
    instance = tmp_path / "instance"
    instance.mkdir()
    env = os.environ.copy()
    env["ZINE_TEST_INSTANCE"] = str(instance)
    result = subprocess.run(
        [sys.executable, "-c", WORKFLOW_SCRIPT],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
