"""Disk-first, sequential public HTTP with persistent blocking and no evasion."""

import fcntl
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx


class SourceBlocked(RuntimeError):
    """The host refused public access; further requests are prohibited."""


class PublicFetcher:
    """Cache raw responses, including errors, and enforce one request/host/second.

    Redirects receive the same host policy. Cache keys include the complete URL.
    A fresh date/season discovery URL is needed to discover new finished matches;
    immutable detail URLs are never fetched twice. No cookies are sent or replayed.
    """

    def __init__(self, data_dir: Path, interval: float = 1.1) -> None:
        if interval < 1:
            raise ValueError("Public sources require >=1 second between requests")
        self.root = data_dir / "raw"
        self.interval = interval
        self.policy = self.root / "source_host_policy.json"

    def fetch(self, source: str, url: str, *, ajax: bool = False) -> Path:
        """Return a cached body or fetch once; fail closed on blocked hosts."""
        self.root.mkdir(parents=True, exist_ok=True)
        # Multiple CLI invocations must not hammer a host or race the block file.
        with (self.root / "source_fetch.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return self._fetch(source, url, ajax=ajax)

    def _fetch(self, source: str, url: str, *, ajax: bool, depth: int = 0) -> Path:
        if depth > 10:
            raise RuntimeError("Too many public redirects")
        # HTML and AJAX JSON are different public representations, not retries.
        # A cached representation (including failures) is never requested twice.
        key = hashlib.sha256(
            (url + ("|ajax-json" if ajax else "")).encode()
        ).hexdigest()
        directory = self.root / source
        directory.mkdir(parents=True, exist_ok=True)
        body = directory / f"{key}.body"
        meta = directory / f"{key}.json"
        if meta.exists():
            record = json.loads(meta.read_text())
            if record.get("blocked"):
                raise SourceBlocked(f"Cached refusal: {url}")
            if record.get("redirect"):
                return self._fetch(
                    source, record["redirect"], ajax=ajax, depth=depth + 1
                )
            if record["status"] != 200:
                raise RuntimeError(f"Cached HTTP {record['status']}: {url}")
            return body
        host = urlparse(url).netloc
        state = json.loads(self.policy.read_text()) if self.policy.exists() else {}
        if state.get(host, {}).get("blocked"):
            raise SourceBlocked(f"Host previously refused access: {host}")
        delay = self.interval - (time.time() - state.get(host, {}).get("last", 0))
        if delay > 0:
            time.sleep(delay)
        state[host] = {"last": time.time(), "blocked": False}
        self.policy.write_text(json.dumps(state, indent=2))
        headers = {"User-Agent": "MatchPulse/0.1 (public football data research)"}
        if ajax:
            # jQuery's documented JSON content negotiation, never a signed token.
            headers.update(
                {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
            )
        with httpx.Client(
            headers=headers,
            timeout=180,
            follow_redirects=False,
        ) as client:
            response = client.get(url)
        body.write_bytes(response.content)
        challenge = "text/html" in response.headers.get("content-type", "") and any(
            token in response.text[:200000].lower()
            for token in ("cf-chl-", "just a moment...", "captcha", "access denied")
        )
        blocked = response.status_code in (403, 429) or challenge
        record = {
            "url": url,
            "status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "bytes": len(response.content),
            "fetched_at": time.time(),
            "blocked": blocked,
        }
        meta.write_text(json.dumps(record, indent=2))
        if blocked:
            state[host]["blocked"] = True
            self.policy.write_text(json.dumps(state, indent=2))
            raise SourceBlocked(f"HTTP {response.status_code}/challenge: {url}")
        if response.is_redirect:
            destination = urljoin(url, response.headers["location"])
            record["redirect"] = destination
            meta.write_text(json.dumps(record, indent=2))
            return self._fetch(source, destination, ajax=ajax, depth=depth + 1)
        response.raise_for_status()
        return body
