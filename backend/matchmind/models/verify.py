"""Read-only model/DB acceptance checks; writes only its local evidence report."""

import json

import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import dict_row

from matchmind.config import get_settings
from matchmind.models.common import catalogue, data_dir, save_json, timestamp
from matchmind.models.gamestate_model import FEATURES, featurize, predict


def main() -> None:
    shots = pd.read_parquet(data_dir() / "processed/xg/shots.parquet")
    windows = pd.read_parquet(data_dir() / "processed/gamestate_windows.parquet")
    sample = windows[
        (windows.match_id == "sb:3869685")
        & (windows.minute == 80)
        & (windows.team == "away")
    ]
    assert len(sample) == 1
    factual = featurize(sample)
    hypothetical = factual.copy()
    hypothetical["score_diff"] -= 1
    bands = predict(pd.concat([factual, hypothetical], ignore_index=True))
    for quantiles in bands.values():
        assert len(quantiles["p50"]) == 2
        assert np.all(np.asarray(quantiles["p10"]) <= quantiles["p50"])
        assert np.all(np.asarray(quantiles["p50"]) <= quantiles["p90"])
    with psycopg.connect(get_settings().database_url, row_factory=dict_row) as conn:
        count = conn.execute(
            """SELECT count(DISTINCT match_id) AS matches, count(*) AS events,
            count(xg) AS xg, count(vaep) AS vaep, count(xt) AS xt FROM events"""
        ).fetchone()
        demo_ids = {m["native_id"] for m in catalogue() if m["demo"]}
        expected_shots = int(shots.game_id.isin(demo_ids).sum())
        assert count["matches"] == len(demo_ids)
        assert count["xg"] == expected_shots
        goals = conn.execute("""SELECT event_id, period, minute, extra->>'id' AS uuid,
            xg, vaep FROM events WHERE match_id='sb:3869685' AND type='Shot'
            AND extra->'shot'->'outcome'->>'name'='Goal'
            ORDER BY period, minute, second""").fetchall()
        lookup = shots.set_index("original_event_id").xg
        assert all(
            g["xg"] is not None
            and np.isclose(g["xg"], lookup[g["uuid"]])
            and g["vaep"] is not None
            for g in goals
        )
        assert sum(g["period"] < 5 for g in goals) == 6
        raw = conn.execute(
            """SELECT sum(xg) AS xg, sum(vaep) AS vaep FROM events
            WHERE match_id='sb:3869685' AND period<5"""
        ).fetchone()
        aggregate = conn.execute(
            """SELECT sum(xg) AS xg, sum(vaep) AS vaep FROM minute_metrics_view
            WHERE match_id='sb:3869685'"""
        ).fetchone()
        assert np.allclose(
            [raw["xg"], raw["vaep"]], [aggregate["xg"], aggregate["vaep"]]
        )
        excluded = conn.execute("""SELECT extra->'pass'->'outcome'->>'name' AS outcome,
            count(*) AS n FROM events WHERE type='Pass' AND vaep IS NULL
            GROUP BY 1 ORDER BY 2 DESC""").fetchall()
    report = {
        "date": timestamp(),
        "counts": count,
        "final_goal_rows": goals,
        "final_events_sums": raw,
        "final_aggregate_sums": aggregate,
        "excluded_pass_outcomes": excluded,
        "game_state_inference": {
            "feature_count": len(FEATURES),
            "sample_features": factual.to_dict("records")[0],
            "factual_and_score_minus_one_bands": bands,
            "label": "modelled sensitivity, not a causal effect",
        },
    }
    save_json("verification.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
