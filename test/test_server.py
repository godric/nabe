import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError

import pytest

from nabe import server, store


@pytest.fixture
def base_url(monkeypatch):
    saved = []
    monkeypatch.setattr(store, "snapshot", lambda: {"devices": [], "groups": []})
    monkeypatch.setattr(store, "save_layout", saved.append)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", saved
    httpd.shutdown()


def request(url, method="GET", body=None):
    req = urllib.request.Request(url, method=method, data=body)  # noqa: S310
    with urllib.request.urlopen(req) as resp:  # noqa: S310
        return resp.status, resp.headers["Content-Type"], resp.read()


def test_serves_the_page_and_api(base_url):
    url, _ = base_url

    assert request(url + "/")[1].startswith("text/html")
    assert request(url + "/app.js")[1].startswith("text/javascript")
    assert request(url + "/favicon.svg")[1] == "image/svg+xml"
    assert request(url + "/apple-touch-icon.png")[1] == "image/png"
    assert request(url + "/manifest.webmanifest")[1] == "application/manifest+json"
    with pytest.raises(HTTPError, match="404"):
        request(url + "/index.html")
    assert json.loads(request(url + "/api/devices")[2]) == {"devices": [], "groups": []}
    with pytest.raises(HTTPError, match="404"):
        request(url + "/nope")


def test_post_probe_asks_for_a_round(base_url):
    url, _ = base_url
    store.probe_requested.clear()

    assert request(url + "/api/probe", "POST", b"")[0] == 200
    assert store.probe_requested.is_set()
    store.probe_requested.clear()


def test_put_layout(base_url):
    url, saved = base_url

    assert request(url + "/api/layout", "PUT", b'{"groups": []}')[0] == 200
    assert saved == [{"groups": []}]
    with pytest.raises(HTTPError, match="400"):
        request(url + "/api/layout", "PUT", b"nope")
