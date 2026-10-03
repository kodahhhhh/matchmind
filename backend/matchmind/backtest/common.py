"""Artifact IO and polite, cache-only-after-first-request source access."""

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from matchmind.config import get_settings


def root() -> Path:
    return get_settings().data_dir


def output() -> Path:
    path = root() / "processed/backtest"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, allow_nan=False, default=str) + "\n"
    )
    temporary.replace(path)


def catalogue() -> list[dict]:
    return json.loads((root() / "catalogue/matches.json").read_text())


class CachedClient:
    """Immutable response cache includes failures and request provenance."""

    def __init__(self) -> None:
        self.last = 0.0
        self.client = httpx.Client(
            headers={"User-Agent": "Mozilla/5.0 (compatible; MatchMindResearch/1.0)"},
            timeout=45,
            follow_redirects=True,
        )

    def get(self, source: str, url: str, **params: Any) -> dict:
        key = str(httpx.URL(url, params=params))
        digest = hashlib.sha256(key.encode()).hexdigest()[:24]
        path = root() / "raw/markets" / source / f"{digest}.json"
        if path.exists():
            return json.loads(path.read_text())
        time.sleep(max(0, 0.26 - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        try:
            response = self.client.get(url, params=params)
            row = {"url": key, "status": response.status_code, "body": response.text}
        except httpx.HTTPError as exc:
            row = {"url": key, "status": 0, "body": str(exc)}
        row["fetched_at"] = datetime.now(UTC).isoformat()
        save(path, row)
        return row

    def json(self, source: str, url: str, **params: Any) -> Any:
        row = self.get(source, url, **params)
        if row["status"] != 200:
            raise RuntimeError(f"Cached request failed: {row['url']} ({row['status']})")
        return json.loads(row["body"])
