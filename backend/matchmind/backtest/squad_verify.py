"""Read-only W12 HTTP acceptance on :8050; leave the shared API untouched."""

import hashlib
import json
from pathlib import Path

import httpx
import pandas as pd

from matchmind.backtest.common import output, root, save
from matchmind.backtest.contracts import Backtest, Market


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main() -> None:
    staged = output() / "w12"
    golden = Path(__file__).resolve().parents[2] / "tests/golden"
    points, responses = 0, 0
    with httpx.Client(base_url="http://127.0.0.1:8050", timeout=60) as client:
        response = client.get("/api/backtest")
        response.raise_for_status()
        actual = response.json()
        Backtest.model_validate(actual)
        assert actual == json.loads((staged / "backtest.json").read_text())
        assert actual == json.loads((golden / "backtest_example.json").read_text())
        assert client.get("/api/matches/sb:0/market").status_code == 404
        assert client.get("/api/matches/not-a-match/market").status_code == 404
        for path in sorted(staged.glob("market_*.json")):
            expected = json.loads(path.read_text())
            response = client.get(f"/api/matches/{expected['match_id']}/market")
            response.raise_for_status()
            Market.model_validate(response.json())
            assert response.json() == expected
            responses += 1
            points += len(expected["series"])
    coverage = pd.read_parquet(output() / "squad_coverage.parquet")
    assert (coverage.valued_xi <= 11).all()
    assert (coverage.live_valued_xi <= 11).all()
    for season, count in [("2015/2016", 306), ("2023/2024", 34)]:
        rows = coverage[
            (coverage.competition == "1. Bundesliga") & (coverage.season == season)
        ]
        assert rows.match_id.nunique() == count
        assert (rows.valued_xi == 11).all()
        assert rows.tm_game.notna().all()
    before = output() / "w12_before"
    # Backtest and old market artifacts remain byte-identical for the running API.
    unchanged = ["backtest.json"] + [p.name for p in before.glob("market_*.json")]
    assert all(digest(output() / name) == digest(before / name) for name in unchanged)
    manifest = {
        p.name: digest(p)
        for p in (root() / "raw/players/transfermarkt").glob("*.csv.gz")
    }
    manifest["player_map.parquet"] = digest(
        root() / "processed/players/player_map.parquet"
    )
    evidence = {
        "api_port": 8050,
        "backtest_golden_equality": True,
        "market_responses": responses,
        "series_points": points,
        "unknown_match_status": 404,
        "original_served_artifacts_unchanged": len(unchanged),
        "bundesliga_full_xi_valuation_coverage": True,
        "source_sha256": manifest,
        "shared_api_action": "No restart; original served artifacts unchanged",
    }
    save(staged / "verification.json", evidence)
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
