import json
from datetime import datetime

from zine.utils import admin
from zine.utils.net import NetException


class RedditResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code
        self.closed = False

    def close(self):
        self.closed = True


def test_reddit_dashboard_parses_current_api_response(monkeypatch):
    payload = {
        "data": {
            "children": [{
                "data": {
                    "author": "example",
                    "created_utc": 0,
                    "score": 42,
                    "title": "Zine on Python 3",
                    "num_comments": 3,
                    "url": "/r/zine/example",
                    "domain": "self.zine",
                    "id": "abc123",
                    "permalink": "/r/zine/comments/abc123/example/",
                }
            }]
        }
    }
    response = RedditResponse(json.dumps(payload).encode())
    requests = []

    def open_reddit(url, **kwargs):
        requests.append((url, kwargs))
        return response

    monkeypatch.setattr(admin, "open_url", open_reddit)
    items = admin.load_zine_reddit()

    assert response.closed
    assert requests[0][0].startswith("https://www.reddit.com/r/zine.json")
    assert requests[0][1]["headers"]["Accept"] == "application/json"
    assert len(items) == 1
    assert items[0]["title"] == "Zine on Python 3"
    assert items[0]["created"] == datetime(1970, 1, 1)
    assert items[0]["url"] == "https://www.reddit.com/r/zine/example"
    assert items[0]["comment_url"].endswith("/comments/abc123/example/")


def test_reddit_dashboard_tolerates_remote_failures(monkeypatch):
    for response in (
        RedditResponse(b"blocked", status_code=403),
        RedditResponse(b"<html>not json</html>"),
        RedditResponse(b"{}"),
    ):
        monkeypatch.setattr(admin, "open_url", lambda *args, **kwargs: response)
        assert admin.load_zine_reddit() == []
        assert response.closed

    def fail(*args, **kwargs):
        raise NetException("offline")

    monkeypatch.setattr(admin, "open_url", fail)
    assert admin.load_zine_reddit() == []
