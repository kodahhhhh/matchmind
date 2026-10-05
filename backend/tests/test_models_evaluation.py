"""Validation guardrails: proper scores, clustered uncertainty and split pinning."""

import numpy as np
import pytest

from matchpulse.models.evaluation import (
    compare,
    freeze_manifest,
    paired_bootstrap,
    probability_metrics,
)


def test_binary_and_multiclass_brier_conventions() -> None:
    y, p = np.array([0, 1]), np.array([0.2, 0.8])
    binary = probability_metrics(y, p)
    multiclass = probability_metrics(y, np.column_stack([1 - p, p]))
    assert binary["brier"] == pytest.approx(0.04)
    assert multiclass["brier"] == pytest.approx(0.08)
    assert binary["log_loss"] == pytest.approx(multiclass["log_loss"])
    assert binary["ece"] == pytest.approx(0.2)


@pytest.mark.parametrize(
    "p",
    [
        np.array([np.nan, 0.5]),
        np.array([-0.1, 0.5]),
        np.array([[0.3, 0.3], [0.2, 0.8]]),
    ],
)
def test_invalid_probabilities_fail_closed(p: np.ndarray) -> None:
    with pytest.raises(ValueError):
        probability_metrics(np.array([0, 1]), p)


def test_manifest_rejects_changed_split_and_preserves_original(tmp_path) -> None:
    path = tmp_path / "split.json"
    freeze_manifest(path, {"train": [1, 2], "test": [3]})
    original = path.read_bytes()
    freeze_manifest(path, {"test": [3], "train": [1, 2]})
    with pytest.raises(ValueError, match="Frozen manifest changed"):
        freeze_manifest(path, {"train": [1, 3], "test": [2]})
    assert path.read_bytes() == original


def test_bootstrap_keeps_correlated_minutes_together() -> None:
    groups = np.array(["a", "a", "b"])
    base, candidate = np.zeros(3), np.array([1.0, 1.0, -1.0])
    result = paired_bootstrap(groups, base, candidate)
    repeated = paired_bootstrap(
        np.repeat(groups, 20), np.repeat(base, 20), np.repeat(candidate, 20)
    )
    assert result == repeated
    assert result["delta"] == pytest.approx(1 / 3)
    assert result["ci95"] == [-1.0, 1.0]
    assert result["matches"] == 2


def test_identical_predictions_have_exactly_zero_paired_interval() -> None:
    y, p = np.array([0, 1, 0]), np.array([0.1, 0.8, 0.3])
    result = compare(y, p, p, np.array([1, 1, 2]))
    for metric in result["paired_ci"].values():
        assert metric["delta"] == 0
        assert metric["ci95"] == [0, 0]


def test_destination_rejects_escape(tmp_path, monkeypatch) -> None:
    import matchpulse.models.evaluate as evaluate

    monkeypatch.setattr(evaluate, "data_dir", lambda: tmp_path)
    with pytest.raises(ValueError):
        evaluate.destination("../production")
    with pytest.raises(ValueError):
        evaluate.destination(".")
    assert evaluate.destination("trial") == tmp_path / "models/candidates/trial"


def test_nested_xg_selection_excludes_outer_test_and_shootouts() -> None:
    from matchpulse.models.xg_experiment import masks

    folds = np.repeat(np.arange(5), 3)
    eligible = np.tile([True, True, False], 5)
    for outer in range(5):
        train, tune, test = masks(folds, eligible, outer)
        assert not (train & tune).any()
        assert not ((train | tune) & test).any()
        assert not ((train | tune) & ~eligible).any()
        assert train.sum() == 6 and tune.sum() == 2 and test.sum() == 3


def test_poisson_scores_handle_zero_and_exact_rate() -> None:
    from matchpulse.models.goals_experiment import poisson_losses

    result = poisson_losses(np.array([0.0, 1.0, 3.0]), np.array([0.2, 1.0, 3.0]))
    assert result["poisson_deviance"] == pytest.approx([0.4, 0, 0])
    assert np.isfinite(result["poisson_log_loss"]).all()
    with pytest.raises(ValueError):
        poisson_losses(np.array([0.0]), np.array([0.0]))


def test_market_checkpoint_uses_three_minute_lag(tmp_path, monkeypatch) -> None:
    import json

    import pandas as pd

    import matchpulse.models.evaluate as evaluate

    monkeypatch.setattr(evaluate, "data_dir", lambda: tmp_path)
    folder = tmp_path / "processed/backtest"
    folder.mkdir(parents=True)
    (folder / "polymarket_alignment.json").write_text(
        json.dumps(
            [
                {
                    "match_id": "sb:1",
                    "aligned": True,
                    "period_offsets": {"1": 0, "2": 900},
                }
            ]
        )
    )
    (folder / "polymarket_histories.json").write_text(
        json.dumps(
            [
                {
                    "match": {"match_id": "sb:1"},
                    "kickoff": 0,
                    "markets": {
                        side: {"prices": {"YES": [{"t": 899, "p": price}]}}
                        for side, price in (("home", 0.5), ("draw", 0.3), ("away", 0.3))
                    },
                }
            ]
        )
    )
    data = pd.DataFrame(
        [
            {"match_id": "sb:1", "period": 1, "minute": 12, "result": 0},
            {"match_id": "sb:1", "period": 1, "minute": 15, "result": 0},
        ]
    )

    def predict(bundle, frame, key="model"):
        assert frame.minute.tolist() == [12]
        return np.array([[0.5, 0.25, 0.25]])

    monkeypatch.setattr(evaluate, "bundle_predict", predict)
    result = evaluate.inplay_markets(data, {}, None, tmp_path)
    assert list(result) == ["15"]
    assert result["15"]["n_matches"] == 1


def test_parquet_sequence_matches_dense_training_and_excludes_shootouts(
    tmp_path,
) -> None:
    import lightgbm as lgb
    import pandas as pd

    from matchpulse.models.vaep_experiment import ParquetSequence

    paths = [tmp_path / f"{i}.parquet" for i in range(3)]
    for i, path in enumerate(paths):
        pd.DataFrame(
            {"a": [i, i + 1, 999], "b": [1.0, 2.0, 999.0], "period_id": [1, 2, 5]}
        ).to_parquet(path)
    seq = ParquetSequence(paths, [2, 2, 2], ["a", "b"])
    expected = np.array([[0, 1], [1, 2], [1, 1], [2, 2], [2, 1], [3, 2]], float)
    np.testing.assert_array_equal(seq[:], expected)
    np.testing.assert_array_equal(seq[1:5], expected[1:5])
    np.testing.assert_array_equal(seq[[1, 4]], expected[[1, 4]])
    with pytest.raises(IndexError):
        seq[6]
    params = {
        "objective": "binary",
        "num_threads": 1,
        "verbosity": -1,
        "min_data_in_leaf": 1,
        "min_data_in_bin": 1,
        "feature_pre_filter": False,
        "seed": 2026,
    }
    y = np.array([0, 1, 0, 1, 0, 1])
    streamed = lgb.train(
        params, lgb.Dataset(seq, label=y, params=params), num_boost_round=3
    )
    dense = lgb.train(
        params, lgb.Dataset(expected, label=y, params=params), num_boost_round=3
    )
    np.testing.assert_allclose(streamed.predict(expected), dense.predict(expected))
    assert seq._load.cache_info().currsize <= 2
    seq.release()
    assert seq._load.cache_info().currsize == 0


def test_quantile_scoring_includes_discrete_zero_outcomes() -> None:
    from matchpulse.models.evaluation import quantile_metrics

    y = np.array([0.0, 1.0])
    p = np.array([[0.0, 0.5, 1.0], [0.0, 0.5, 1.0]])
    result = quantile_metrics(y, p)
    assert result["coverage_p10_p90"] == 1
    assert result["pinball"]["p50"] == 0.25
    assert result["fraction_at_or_below"]["p10"] == 0.5
    with pytest.raises(ValueError, match="crossing"):
        quantile_metrics(y, p[:, ::-1])


def test_weighted_bootstrap_equals_expanded_action_rows() -> None:
    a = paired_bootstrap(
        np.array([1, 2]), np.zeros(2), np.array([1.0, -1.0]), weights=np.array([2, 1])
    )
    b = paired_bootstrap(np.array([1, 1, 2]), np.zeros(3), np.array([1.0, 1.0, -1.0]))
    assert a == b


def test_xt_transition_model_reproduces_socceraction_grid() -> None:
    import pandas as pd
    from socceraction.spadl import config
    from socceraction.xthreat import ExpectedThreat

    from matchpulse.models.xt_experiment import (
        solve,
        transition_counts,
        transition_probabilities,
    )

    records = []
    for y in range(8):
        for x in range(12):
            for action in ("pass", "shot"):
                result = "success" if action == "pass" or x > 8 else "fail"
                records.append(
                    {
                        "period_id": 1,
                        "type_name": action,
                        "result_name": result,
                        "type_id": config.actiontypes.index(action),
                        "result_id": config.results.index(result),
                        "start_x": (x + 0.5) * 105 / 12,
                        "start_y": (y + 0.5) * 68 / 8,
                        "end_x": (min(x + 1, 11) + 0.5) * 105 / 12,
                        "end_y": (y + 0.5) * 68 / 8,
                    }
                )
    actions = pd.DataFrame(records)
    counts = transition_counts(actions)
    actual = solve(transition_probabilities(counts, False))
    reference = ExpectedThreat(l=12, w=8).fit(actions).xT
    np.testing.assert_allclose(actual, reference, atol=1e-12)
    symmetric = solve(transition_probabilities(counts, True))
    np.testing.assert_allclose(symmetric, symmetric[::-1])


def test_lineup_prior_and_player_totals_exclude_the_windows_own_match() -> None:
    import pandas as pd

    from matchpulse.models.player_ratings import lineup_from_table

    ratings = pd.DataFrame(
        {
            "game_id": [1, 1, 2, 2],
            "player_id": [10, 20, 10, 20],
            "minutes": [90.0, 90.0, 90.0, 90.0],
            "vaep": [5.0, 9.0, 0.1, 0.2],
        }
    )
    windows = pd.DataFrame(
        {"game_id": [1], "on_pitch_for": [[10]], "on_pitch_against": [[20]]}
    )
    before = lineup_from_table(windows, ratings, exclude_own_prior=True)
    ratings.loc[ratings.game_id == 1, "vaep"] = [50000.0, 90000.0]
    after = lineup_from_table(windows, ratings, exclude_own_prior=True)
    np.testing.assert_allclose(before, after, atol=1e-10)


def test_outer_lineup_never_reads_global_oof_values(monkeypatch) -> None:
    import pandas as pd

    import matchpulse.models.player_ratings as ratings

    def global_values():
        raise AssertionError("Global OOF values leak upstream outer-fold training")

    def outer_values(fold):
        assert fold == 2
        return pd.DataFrame(
            {"game_id": [1], "player_id": [10], "minutes": [90.0], "vaep": [0.3]}
        )

    monkeypatch.setattr(ratings, "table", global_values)
    monkeypatch.setattr(ratings, "outer_table", outer_values)
    windows = pd.DataFrame(
        {"game_id": [99], "on_pitch_for": [[10]], "on_pitch_against": [[20]]}
    )
    result = ratings.lineup_features(windows, 2)
    assert result.lineup_vaep_for.iloc[0] == pytest.approx(0.3)
    assert result.lineup_vaep_against.iloc[0] == pytest.approx(0.3)


def test_new_source_shot_context_is_missing_and_score_is_pre_shot() -> None:
    from matchpulse.models.xg_augmentation import extract

    meta = {"match_id": "af:1", "home": {"id": 1}, "away": {"id": 2}}
    event = {
        "id": "one",
        "period": 1,
        "minute": 2,
        "team": {"id": 1},
        "type": {"name": "Shot"},
        "location": [100, 40],
        "shot": {
            "outcome": {"name": "Goal"},
            "type": {"name": "Open Play"},
            "body_part": {"name": "Right Foot"},
        },
    }
    rows = extract(meta, [event, {**event, "id": "two"}])
    assert rows[0]["score_diff"] == 0 and rows[1]["score_diff"] == 1
    assert rows[0]["goal"] == 1
    assert np.isnan(rows[0]["under_pressure"])
    assert np.isnan(rows[0]["technique"])
    assert rows[0]["freeze_frame_present"] == 0


def test_distributional_result_probabilities_keep_tail_and_symmetry():
    from matchpulse.backtest.inplay_poisson import result_probabilities

    diff = np.array([0, 1, -2, 0])
    home = np.array([1.2, 0.6, 2.5, 0.0])
    away = np.array([0.9, 2.0, 0.2, 0.0])
    p = result_probabilities(diff, home, away)
    reverse = result_probabilities(-diff, away, home)
    np.testing.assert_allclose(p.sum(axis=1), 1)
    np.testing.assert_allclose(p, reverse[:, ::-1], atol=1e-14)
    assert p[-1, 1] > 1 - 1e-8
    assert (p >= 0).all()


def test_remaining_goal_labels_exclude_extra_time_and_reverse_own_goals():
    from matchpulse.backtest.inplay_poisson import regulation_goals

    def event(period, team, kind):
        return {
            "period": period,
            "team": {"id": team},
            "type": {"name": kind},
            "shot": {"outcome": {"name": "Goal"}},
        }

    assert regulation_goals(
        {"home": {"id": 1}},
        [event(1, 1, "Shot"), event(2, 1, "Own Goal Against"), event(3, 1, "Shot")],
    ) == (1, 1)
