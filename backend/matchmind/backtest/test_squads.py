"""Leakage and live-roster regression tests owned by W12."""

import copy

import numpy as np
import pandas as pd
import pytest

from matchmind.backtest.squad_train import offset_predict
from matchmind.backtest.squads import match_games, player_map
from matchmind.models.squad import live_strength, team_features, value_before


def test_valuation_excludes_same_day_and_future_updates() -> None:
    history = pd.DataFrame(
        {
            "player_id": [1, 1, 1],
            "date": pd.to_datetime(["2020-01-01", "2020-02-01", "2021-01-01"]),
            "market_value_in_eur": [100, 999, 9999],
        }
    )
    assert value_before(history, 1, pd.Timestamp("2020-02-01")) == 100
    changed = history.copy()
    changed.loc[changed.date >= "2020-02-01", "market_value_in_eur"] = 1e12
    assert value_before(changed, 1, pd.Timestamp("2020-02-01")) == 100
    assert np.isnan(value_before(history, 1, pd.Timestamp("2019-01-01")))


def test_missing_usual_starters_use_previous_lineups_only() -> None:
    def features(previous: list[list[int]]) -> dict:
        return team_features(
            [1],
            [2],
            pd.Timestamp("2020-01-01"),
            {1: 100, 2: 200},
            {1: pd.Timestamp("2000-01-01")},
            previous,
            {1: 3},
            {1: True},
        )

    assert np.isnan(features([])["missing_starters_log_value"])
    assert features([[1, 2]] * 3)["missing_starters_log_value"] == pytest.approx(
        np.log1p(200)
    )
    assert features([[1, 2]] * 3)["observed_caps"] == 3
    assert features([[1, 2]] * 3)["new_signings_share"] == 1


def event(
    index: int, kind: str, team: int, minute: int = 0, period: int = 1, **extra
) -> dict:
    return {
        "index": index,
        "period": period,
        "minute": minute,
        "second": 0,
        "team": {"id": team},
        "type": {"name": kind},
        **extra,
    }


def test_live_subs_reds_future_invariance_and_bench_dismissals() -> None:
    events = [
        event(1, "Starting XI", 10, tactics={"lineup": [{"player": {"id": 1}}]}),
        event(2, "Starting XI", 20, tactics={"lineup": [{"player": {"id": 2}}]}),
        event(
            3,
            "Substitution",
            10,
            45,
            2,
            player={"id": 1},
            substitution={"replacement": {"id": 3}},
        ),
        event(
            4,
            "Bad Behaviour",
            20,
            60,
            2,
            player={"id": 99},
            bad_behaviour={"card": {"name": "Red Card"}},
        ),
        event(
            5,
            "Foul Committed",
            10,
            70,
            2,
            player={"id": 3},
            foul_committed={"card": {"name": "Second Yellow"}},
        ),
    ]
    boundaries = pd.DataFrame(
        [(1, 45), (2, 45), (2, 46), (2, 61), (2, 70), (2, 71)],
        columns=["period", "minute"],
    )
    values = {1: 100, 2: 100, 3: 1000}
    result = live_strength(events, values, boundaries)
    assert result.pitch_log_value_diff.iloc[0] == 0
    assert result.pitch_log_value_diff.iloc[1] == 0  # strict boundary
    assert result.pitch_log_value_diff.iloc[2] > 0
    assert result.pitch_log_value_diff.iloc[3] == result.pitch_log_value_diff.iloc[2]
    assert result.pitch_log_value_diff.iloc[4] > 0
    assert np.isnan(result.pitch_log_value_diff.iloc[5])
    changed = copy.deepcopy(events)
    changed[-1]["minute"] = 89
    pd.testing.assert_frame_equal(
        result.iloc[:5], live_strength(changed, values, boundaries).iloc[:5]
    )


def test_ambiguous_game_match_is_rejected_and_scores_not_used() -> None:
    games = pd.DataFrame(
        [
            {
                "game_id": 1,
                "date": pd.Timestamp("2020-01-01"),
                "home_club_name": "Bayern Munich",
                "away_club_name": "Bayer 04 Leverkusen",
            }
        ]
    )
    matches = [
        {
            "native_id": 1,
            "match_id": "sb:1",
            "match_date": "2020-01-01",
            "home": {"name": "Bayern Munich"},
            "away": {"name": "Bayer Leverkusen"},
            "competition": "Bundesliga",
            "season": "2020",
        }
    ]
    assert len(match_games(matches, games)[0]) == 1
    assert not match_games(matches, pd.concat([games, games]))[0]
    matches[0]["match_date"] = "2020-01-02"
    assert not match_games(matches, games)[0]


def test_w11_confidence_filter(tmp_path, monkeypatch) -> None:
    folder = tmp_path / "processed/players"
    folder.mkdir(parents=True)
    pd.DataFrame(
        {
            "sb_player_id": [1, 2, 3],
            "tm_player_id": [10, 20, 30],
            "confidence": [0.8, 0.79, 1.0],
        }
    ).to_parquet(folder / "player_map.parquet")
    monkeypatch.setattr("matchmind.backtest.squads.root", lambda: tmp_path)
    assert player_map() == {}
    (folder / "_READY").touch()
    assert player_map() == {1: 10, 3: 30}


def test_offset_model_missing_columns_and_probability_support() -> None:
    x = np.array([[1, np.nan], [2, np.nan], [3, np.nan], [4, np.nan]])
    p = offset_predict(
        x,
        np.array([0, 1, 2, 0]),
        np.full((4, 3), 1 / 3),
        np.array([[np.nan, np.nan], [1e12, 0]]),
        np.full((2, 3), 1 / 3),
        100.0,
    )
    np.testing.assert_allclose(p.sum(axis=1), 1)
    assert np.isfinite(p).all()
    assert (p > 0).all()


def test_staged_report_conservation_and_frozen_slippage() -> None:
    import json

    from matchmind.backtest.common import output
    from matchmind.backtest.contracts import Backtest

    path = output() / "w12/backtest.json"
    if not path.exists():
        pytest.skip("Run W12 pipeline first")
    report = Backtest.model_validate_json(path.read_text())
    before = json.loads((output() / "w12_before/backtest.json").read_text())
    baseline = {s["id"]: s for s in before["strategies"]}
    assert len(report.comparison) == len(report.strategies) == 7
    for strategy, comparison in zip(report.strategies, report.comparison, strict=True):
        assert strategy.id == comparison.strategy_id
        assert comparison.before.pnl == baseline[strategy.id]["pnl"]
        assert comparison.after.pnl == strategy.pnl
        assert strategy.n_bets == len(strategy.bets)
        assert strategy.pnl == pytest.approx(sum(b.pnl for b in strategy.bets))
        assert strategy.roi == pytest.approx(strategy.pnl / strategy.staked)
        assert strategy.equity[-1].bankroll - strategy.equity[
            0
        ].bankroll == pytest.approx(strategy.pnl)
    scenarios = [s for s in report.strategies if s.market == "polymarket"]
    for cents, scenario in enumerate(scenarios):
        assert len(scenario.bets) == len(scenarios[0].bets)
        for a, b in zip(scenarios[0].bets, scenario.bets, strict=True):
            assert (a.match_id, a.outcome, a.side, a.minute, a.stake, a.model_prob) == (
                b.match_id,
                b.outcome,
                b.side,
                b.minute,
                b.stake,
                b.model_prob,
            )
            assert b.price_or_odds == pytest.approx(a.price_or_odds + cents / 100)


def test_staged_market_uses_retained_model_with_existing_lag() -> None:

    from matchmind.backtest.common import output
    from matchmind.backtest.contracts import Market
    from matchmind.backtest.polymarket import INFORMATION_LAG_MINUTES

    paths = list((output() / "w12").glob("market_*.json"))
    if not paths:
        pytest.skip("Run W12 pipeline first")
    predictions = pd.read_parquet(output() / "inplay_predictions.parquet").set_index(
        ["match_id", "period", "minute"]
    )
    count = 0
    for path in paths:
        market = Market.model_validate_json(path.read_text())
        for row in market.series:
            p = predictions.loc[
                (market.match_id, row.period, row.minute - INFORMATION_LAG_MINUTES)
            ]
            for side in ("home", "draw", "away"):
                assert getattr(row.model, side) == pytest.approx(p[f"p_{side}"])
            count += 1
    assert count > 0
