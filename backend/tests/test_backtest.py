"""Causality, settlement, accounting and the precomputed route boundary."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from matchpulse.api.routes import backtest as routes
from matchpulse.backtest.common import catalogue, output, root
from matchpulse.backtest.contracts import Backtest, Market
from matchpulse.backtest.inplay import split
from matchpulse.backtest.markets import align, last_price, outcome, scheduled
from matchpulse.backtest.prematch import predictions, result_probability
from matchpulse.backtest.statistics import roi_interval, scores, summary


def test_poisson_support_and_symmetry() -> None:
    p = result_probability(1.4, 1.4)
    assert p.sum() == pytest.approx(1)
    assert p[0] == pytest.approx(p[2])
    assert result_probability(3, 0.3)[0] > 0.8
    assert result_probability(0.3, 3)[2] > 0.8


def test_future_and_same_round_results_cannot_change_predictions() -> None:
    rows = []
    for week in range(1, 35):
        for h, a in [(1, 2), (3, 4)]:
            rows.append(
                {
                    "round": week,
                    "home": {"id": h},
                    "away": {"id": a},
                    "home_score": 1,
                    "away_score": 0,
                    "xg_home": 1.1,
                    "xg_away": 0.8,
                }
            )
    p = predictions(rows, 0.95, 8, 0.5)
    changed = copy.deepcopy(rows)
    for row in changed:
        if row["round"] >= 18:
            row.update(home_score=12, away_score=7, xg_home=10, xg_away=6)
    after = predictions(changed, 0.95, 8, 0.5)
    # Includes both matches of week 18; week 18 labels first affect week 19.
    np.testing.assert_array_equal(p[:36], after[:36])
    assert not np.array_equal(p[36:], after[36:])


def test_asof_is_strict_and_never_interpolates_stale_or_future_prices() -> None:
    history = [{"t": 100, "p": 0.2}, {"t": 160, "p": 0.9}]
    assert last_price(history, 160) == 0.2
    assert last_price(history, 161) == 0.9
    assert last_price(history, 100) is None
    assert last_price(history, 251) is None
    assert last_price(list(reversed(history)), 161) == 0.9


def test_entire_test_tournaments_are_excluded() -> None:
    matches = [m for m in catalogue() if m["training"]]
    tournaments = [
        m
        for m in matches
        if (m["competition"], m["season"])
        in {
            ("UEFA Euro", "2024"),
            ("Copa America", "2024"),
            ("FIFA World Cup", "2022"),
        }
    ]
    assert len(tournaments) == 147
    assert all(split(m) == "backtest" for m in tournaments)
    upstream = [m for m in matches if split(m) == "upstream"]
    assert len(upstream) == 397
    assert all(m["match_date"] < "2015-08-01" for m in upstream)
    assert (
        split({"competition": "X", "season": "2024", "match_date": "2024-01-01"})
        == "excluded"
    )


def test_probability_scores_and_match_cluster_accounting() -> None:
    result = scores(np.array([0, 1, 2]), np.full((3, 3), 1 / 3))
    assert result["brier"] == pytest.approx(2 / 3)
    assert result["log_loss"] == pytest.approx(np.log(3))
    bets = [
        {"match_id": "a", "stake": 100, "pnl": 100},
        {"match_id": "a", "stake": 100, "pnl": -100},
        {"match_id": "b", "stake": 100, "pnl": 0},
    ]
    assert roi_interval(bets, ["a", "b", "c"]) == [0, 0]
    report = summary(
        bets,
        ["a", "b", "c"],
        [
            {"bankroll": 1000},
            {"bankroll": 1100},
            {"bankroll": 950},
        ],
    )
    assert report["pnl"] == 0
    assert report["staked"] == 300
    assert report["max_drawdown"] == 150


def test_actual_catalogue_clock_is_cross_checked_not_assumed_local() -> None:
    match = {
        "match_date": "2024-07-05",
        "kick_off": "16:00:00",
        "competition": "UEFA Euro",
    }
    event = {"markets": [{"gameStartTime": "2024-07-05 16:00:00+00"}]}
    timestamp, evidence = scheduled(match, event)
    assert timestamp == 1720195200
    assert evidence["clock_interpretation"] == "UTC"
    event["markets"][0]["gameStartTime"] = "2024-07-06 16:00:00+00"
    assert scheduled(match, event)[0] is None


def test_market_outcome_mapping_rejects_qualification_and_player_props() -> None:
    match = {"home": {"name": "Argentina"}, "away": {"name": "France"}}
    assert outcome({"question": "Will Argentina win?"}, match) == "home"
    assert outcome({"question": "Will the match be a draw?"}, match) == "draw"
    assert (
        outcome({"question": "Who will advance: France vs Argentina?"}, match) is None
    )
    assert outcome({"question": "Will Benzema play for France?"}, match) is None


def test_market_subject_not_opponent_defines_binary_outcome() -> None:
    match = {"home": {"name": "Germany"}, "away": {"name": "Scotland"}}
    assert outcome({"question": "Will Scotland Win vs. Germany?"}, match) == "away"
    assert outcome({"question": "Will Germany Win vs. Scotland?"}, match) == "home"


def test_outcome_subject_accepts_the_netherlands() -> None:
    match = {"home": {"name": "Austria"}, "away": {"name": "Netherlands"}}
    assert outcome({"question": "Will the Netherlands win?"}, match) == "away"


def test_alignment_fails_closed_without_goals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("matchpulse.backtest.markets.match_goals", lambda m: ([], 2800))
    result = align({"match": {"match_id": "sb:1"}, "kickoff": 1000, "markets": {}})
    assert result["aligned"] is False


def test_precomputed_routes_and_path_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "processed/backtest"
    directory.mkdir(parents=True)
    fixture = {
        "generated_at": "2026-10-03T00:00:00Z",
        "sources": [],
        "strategies": [],
        "caveats": ["No trades."],
    }
    (directory / "backtest.json").write_text(json.dumps(fixture))
    monkeypatch.setattr(
        routes, "get_settings", lambda: SimpleNamespace(data_dir=tmp_path)
    )
    with TestClient(routes.app) as client:
        assert client.get("/api/backtest").json() == fixture
        assert client.get("/api/matches/sb:999/market").status_code == 404
        assert client.get("/api/matches/not-a-match/market").status_code == 404
        (directory / "backtest.json").write_text("{bad")
        assert client.get("/api/backtest").status_code == 503


def test_saved_results_contract_and_conservation() -> None:
    path = output() / "backtest.json"
    if not path.exists():
        pytest.skip("Run the historical pipeline first")
    report = Backtest.model_validate_json(path.read_text())
    for strategy in report.strategies:
        assert strategy.n_bets == len(strategy.bets)
        assert strategy.staked == pytest.approx(sum(b.stake for b in strategy.bets))
        assert strategy.pnl == pytest.approx(sum(b.pnl for b in strategy.bets))
        assert strategy.equity[-1].bankroll - strategy.equity[
            0
        ].bankroll == pytest.approx(strategy.pnl)
        assert strategy.roi == pytest.approx(strategy.pnl / strategy.staked)
        if strategy.market == "polymarket":
            keys = [(b.match_id, b.outcome) for b in strategy.bets]
            assert len(keys) == len(set(keys))
            assert all(b.minute <= 85 and b.stake == 100 for b in strategy.bets)
    for path in output().glob("market_*.json"):
        market = Market.model_validate_json(path.read_text())
        assert len({r.index for r in market.series}) == len(market.series)
        assert market.aligned or not market.bets


def test_regulation_final_label_and_minute_boundary() -> None:
    path = output() / "features/3869685.parquet"
    if not path.exists():
        pytest.skip("Run the historical feature builder first")
    import pandas as pd

    frame = pd.read_parquet(path)
    assert set(frame.result) == {1}  # 2–2 in regulation, regardless of shootout winner.
    at79 = frame[(frame.period == 2) & (frame.minute == 79)].iloc[0]
    at80 = frame[(frame.period == 2) & (frame.minute == 80)].iloc[0]
    at81 = frame[(frame.period == 2) & (frame.minute == 81)].iloc[0]
    assert (at79.score_home, at79.score_away) == (2, 0)
    assert (at80.score_home, at80.score_away) == (2, 1)
    assert (at81.score_home, at81.score_away) == (2, 2)


def test_saved_model_partitions_are_disjoint() -> None:
    path = root() / "models/backtest_inplay.json"
    if not path.exists():
        pytest.skip("Run model training first")
    report = json.loads(path.read_text())
    sets = [set(part["match_ids"]) for part in report["splits"].values()]
    upstream = set(
        json.loads((root() / "models/backtest_vaep.json").read_text())[
            "training_match_ids"
        ]
    )
    sets.append(upstream)
    assert sum(map(len, sets)) == len(set.union(*sets))


@pytest.mark.parametrize("name", ["backtest", "market"])
def test_golden_contracts_match_real_precomputed_route(name: str) -> None:
    golden = Path(__file__).with_name("golden") / f"{name}_example.json"
    if not golden.exists() or not (output() / "backtest.json").exists():
        pytest.skip("Generate W10 artifacts and golden responses first")
    expected = json.loads(golden.read_text())
    endpoint = (
        "/api/backtest"
        if name == "backtest"
        else f"/api/matches/{expected['match_id']}/market"
    )
    with TestClient(routes.app) as client:
        response = client.get(endpoint)
    assert response.status_code == 200
    assert response.json() == expected
    (Backtest if name == "backtest" else Market).model_validate(response.json())


def test_future_goals_cannot_change_entry_decisions() -> None:
    from matchpulse.backtest.polymarket import entry_allowed

    future = [{"period": 2, "seconds": 3601, "side": "home"}]
    assert entry_allowed(2, 60, [])
    assert entry_allowed(2, 60, future)
    assert not entry_allowed(2, 61, future)
    assert entry_allowed(2, 64, future)
    assert not entry_allowed(2, 86, [])


def test_slippage_sensitivity_reprices_identical_entries() -> None:
    path = output() / "backtest.json"
    if not path.exists():
        pytest.skip("Run the historical pipeline first")
    report = json.loads(path.read_text())
    scenarios = [s for s in report["strategies"] if s["market"] == "polymarket"]
    base = scenarios[0]["bets"]
    for cents, scenario in enumerate(scenarios):
        assert len(scenario["bets"]) == len(base)
        for original, bet in zip(base, scenario["bets"], strict=True):
            for key in ("match_id", "outcome", "side", "minute", "stake", "model_prob"):
                assert bet[key] == original[key]
            assert bet["price_or_odds"] == pytest.approx(
                original["price_or_odds"] + cents / 100
            )
            assert bet["pnl"] <= original["pnl"]
