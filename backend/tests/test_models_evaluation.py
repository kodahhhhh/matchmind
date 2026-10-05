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
    (folder / "market_sb_1.json").write_text(
        json.dumps(
            {
                "match_id": "sb:1",
                "aligned": True,
                "series": [
                    {
                        "minute": 15,
                        "period": 1,
                        "market": {"home": 0.5, "draw": 0.3, "away": 0.3},
                    },
                    {
                        "minute": 45,
                        "period": 2,
                        "market": {"home": 0.5, "draw": 0.3, "away": 0.3},
                    },
                ],
            }
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
