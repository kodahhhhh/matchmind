from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from matchpulse.models.lite import chance_summary, snapshot
from matchpulse.models.xg_shot import features, predict, statsbomb_features


def test_shot_features_ignore_outcome_provider_and_unknown_context():
    s = pd.DataFrame(
        [
            {
                "x": 94.0,
                "y": 34.0,
                "body_part": "RightFoot",
                "situation": "Penalty",
                "result": "Goal",
                "provider_xg": 0.99,
            }
        ]
    )
    a = features(s)
    s["result"], s["provider_xg"] = "Miss", 0.001
    pd.testing.assert_frame_equal(a, features(s))
    assert a.distance.iloc[0] == 11
    assert a.situation.iloc[0] == 3
    s["body_part"], s["situation"] = None, "Unmapped"
    assert features(s)[["body_part", "situation"]].isna().all().all()
    s["x"] = 110
    with pytest.raises(ValueError):
        features(s)


def test_reduction_matches_shared_geometry_and_categories():
    sb = pd.DataFrame(
        [
            {
                "x": 90.0,
                "y_offset": 10.0,
                "distance": np.hypot(15, 10),
                "angle": np.arctan2(7.32 * 15, 15**2 + 10**2 - (7.32 / 2) ** 2),
                "body_part": 2.0,
                "shot_type": 2.0,
                "set_piece": 1,
            }
        ]
    )
    source = pd.DataFrame(
        [{"x": 90.0, "y": 44.0, "body_part": "Header", "situation": "FromCorner"}]
    )
    pd.testing.assert_frame_equal(
        statsbomb_features(sb), features(source), check_dtype=False
    )
    source.y = 24.0
    pd.testing.assert_frame_equal(
        statsbomb_features(sb), features(source), check_dtype=False
    )


def test_prediction_excludes_own_goals_and_shootouts(tmp_path: Path):
    import lightgbm as lgb

    from matchpulse.models.xg_shot import FEATURES

    s = pd.DataFrame(
        [{"x": 94.0, "y": 34.0, "body_part": "RightFoot", "situation": "Penalty"}] * 10
    )
    m = lgb.LGBMClassifier(n_estimators=1, n_jobs=1, verbosity=-1).fit(
        features(s), [0, 1] * 5
    )
    path = tmp_path / "shot.txt"
    m.booster_.save_model(str(path))
    s["period"], s["result"] = 1, "Goal"
    s.loc[0, "period"] = 5
    s.loc[1, "result"] = "OwnGoal"
    p = predict(s, path)
    assert p.iloc[:2].isna().all() and p.iloc[2:].notna().all()
    assert m.booster_.feature_name() == FEATURES


def test_lite_snapshot_respects_periods_and_excludes_current_minute():
    shots = pd.DataFrame(
        [
            {"id": "a", "team": "home", "period": 1, "minute": 47, "xg": 0.2},
            {"id": "b", "team": "away", "period": 2, "minute": 45, "xg": 0.3},
            {"id": "c", "team": "home", "period": 2, "minute": 46, "xg": 0.4},
        ]
    )
    s = snapshot(shots, period=2, minute=46, score={"home": 0, "away": 1})
    assert s["xg_home"] == 0.2 and s["xg_away"] == 0.3
    assert s["recent_xg_home"] == 0 and s["score_diff"] == -1
    shots.loc[0, "period"] = np.nan
    with pytest.raises(ValueError, match="periods"):
        snapshot(shots, period=2, minute=46, score={"home": 0, "away": 1})
    report = chance_summary(shots)
    assert report["teams"]["home"]["xg"] == pytest.approx(0.6)
    assert report["teams"]["home"]["evidence_ids"] == ["a", "c"]
    assert not report["capabilities"]["possession"]
