"""Acquisition policy regression tests: no live provider calls."""

import json

import httpx
import pytest

from matchpulse.sources.fetch import PublicFetcher, SourceBlocked


def client(monkeypatch: pytest.MonkeyPatch, handler: object) -> None:
    original = httpx.Client
    monkeypatch.setattr(
        "matchpulse.sources.fetch.httpx.Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )


def test_disk_cache_does_not_refetch(tmp_path, monkeypatch) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["user-agent"].startswith("MatchPulse/")
        assert "cookie" not in request.headers
        return httpx.Response(200, json={"immutable": True})

    client(monkeypatch, handler)
    fetcher = PublicFetcher(tmp_path)
    first = fetcher.fetch("example", "https://example.test/data")
    assert fetcher.fetch("example", "https://example.test/data") == first
    assert len(requests) == 1
    assert json.loads(first.read_text()) == {"immutable": True}


@pytest.mark.parametrize("status", [403, 429])
def test_refusal_blocks_host_across_instances_and_sources(
    tmp_path, monkeypatch, status
) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, text="refused")

    client(monkeypatch, handler)
    with pytest.raises(SourceBlocked):
        PublicFetcher(tmp_path).fetch("one", "https://example.test/first")
    with pytest.raises(SourceBlocked):
        PublicFetcher(tmp_path).fetch("two", "https://example.test/other")
    with pytest.raises(SourceBlocked):
        PublicFetcher(tmp_path).fetch("one", "https://alternate.test/other")
    assert len(requests) == 1
    assert next((tmp_path / "raw/one").glob("*.body")).read_text() == "refused"


def test_challenge_200_stops_source(tmp_path, monkeypatch) -> None:
    client(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            text="<title>Just a moment...</title>",
            headers={"Content-Type": "text/html"},
        ),
    )
    with pytest.raises(SourceBlocked):
        PublicFetcher(tmp_path).fetch("one", "https://example.test/a")


def test_redirect_retains_each_raw_response_and_rates_same_host(
    tmp_path, monkeypatch
) -> None:
    calls, sleeps = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/first":
            return httpx.Response(
                302, text="original redirect", headers={"location": "/last"}
            )
        return httpx.Response(200, json={"final": True})

    client(monkeypatch, handler)
    monkeypatch.setattr("matchpulse.sources.fetch.time.sleep", sleeps.append)
    f = PublicFetcher(tmp_path)
    p = f.fetch("one", "https://example.test/first")
    assert json.loads(p.read_text()) == {"final": True}
    assert f.fetch("one", "https://example.test/first") == p
    assert len(calls) == 2 and len(sleeps) == 1 and sleeps[0] >= 1
    assert "original redirect" in [
        p.read_text() for p in (tmp_path / "raw/one").glob("*.body")
    ]


def test_public_html_and_ajax_have_independent_immutable_caches(
    tmp_path, monkeypatch
) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404)

    client(monkeypatch, handler)
    f = PublicFetcher(tmp_path)
    with pytest.raises(httpx.HTTPStatusError):
        f.fetch("one", "https://example.test/a")
    f.fetch("one", "https://example.test/a", ajax=True)
    f.fetch("one", "https://example.test/a", ajax=True)
    with pytest.raises(RuntimeError):
        f.fetch("one", "https://example.test/a")
    assert len(calls) == 2


def test_reject_unsafe_rate_limit(tmp_path) -> None:
    with pytest.raises(ValueError):
        PublicFetcher(tmp_path, interval=0.5)
