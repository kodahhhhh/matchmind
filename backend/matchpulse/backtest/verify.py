"""Read-only acceptance against W10 :8030 and the shared timeline on :8000."""

import json
from pathlib import Path

import httpx

from matchpulse.backtest.common import output, save
from matchpulse.backtest.contracts import Backtest, Market


def main() -> None:
    golden = Path(__file__).resolve().parents[2] / "tests/golden"
    with httpx.Client(timeout=30) as client:
        response = client.get("http://127.0.0.1:8030/api/backtest")
        response.raise_for_status()
        report = response.json()
        Backtest.model_validate(report)
        assert report == json.loads((golden / "backtest_example.json").read_text())
        example = json.loads((golden / "market_example.json").read_text())
        response = client.get(
            f"http://127.0.0.1:8030/api/matches/{example['match_id']}/market"
        )
        response.raise_for_status()
        assert response.json() == example
        assert (
            client.get("http://127.0.0.1:8030/api/matches/sb:0/market").status_code
            == 404
        )
        checked, points = [], 0
        for path in sorted(output().glob("market_*.json")):
            expected = json.loads(path.read_text())
            mid = expected["match_id"]
            response = client.get(f"http://127.0.0.1:8030/api/matches/{mid}/market")
            response.raise_for_status()
            actual = response.json()
            Market.model_validate(actual)
            assert actual == expected
            if not actual["aligned"]:
                continue
            response = client.get(f"http://127.0.0.1:8000/api/matches/{mid}/timeline")
            response.raise_for_status()
            timeline = {r["index"]: r for r in response.json()["minutes"]}
            for row in actual["series"]:
                assert all(
                    row[k] == timeline[row["index"]][k]
                    for k in ("period", "minute", "label")
                )
                points += 1
            checked.append(mid)
    evidence = {
        "endpoints": "GET /api/backtest; GET /api/matches/{id}/market",
        "golden_equality": True,
        "unknown_match_status": 404,
        "market_responses": len(list(output().glob("market_*.json"))),
        "aligned_timeline_matches": checked,
        "timeline_points": points,
        "shared_api_action": "read-only timeline requests; no restart",
    }
    save(output() / "verification.json", evidence)
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
