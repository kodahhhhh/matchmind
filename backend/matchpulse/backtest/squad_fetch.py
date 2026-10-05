"""Cache the explicitly authorized CC0 Transfermarkt dataset, never scrape sites."""

import fcntl
import gzip
import time
from pathlib import Path

import httpx

from matchpulse.backtest.common import root

TABLES = (
    "players",
    "player_valuations",
    "games",
    "game_lineups",
    "appearances",
    "clubs",
)
BASE = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data"


def fetch() -> None:
    destination = root() / "raw/players/transfermarkt"
    destination.mkdir(parents=True, exist_ok=True)
    for table in TABLES:
        path = destination / f"{table}.csv.gz"
        with path.with_suffix(".lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if path.exists():
                print("Reuse", path, flush=True)
                continue
            temporary = Path(str(path) + ".w12.tmp")
            with httpx.stream(
                "GET", f"{BASE}/{table}.csv.gz", timeout=180, follow_redirects=True
            ) as response:
                response.raise_for_status()
                with temporary.open("wb") as target:
                    for block in response.iter_bytes():
                        target.write(block)
            with gzip.open(temporary, "rb") as source:
                while source.read(1024 * 1024):
                    pass
            temporary.replace(path)
            print("Downloaded", table, path.stat().st_size, flush=True)
            time.sleep(0.3)


if __name__ == "__main__":
    fetch()
