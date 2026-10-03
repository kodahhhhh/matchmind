"""Read-only acceptance against an isolated API; save evidence outside git.

DATA_DIR=/home/ubuntu/hackathon/data uv run python tests/run_whatif_sweep.py \
    --url http://127.0.0.1:8020 --output /tmp/matchmind-whatif-sweep.json
"""

import argparse
import json
import random
import time
from collections import Counter
from pathlib import Path

import httpx
import numpy as np

from matchmind.api.counterfactual import inference_inputs, training_analogs
from matchmind.api.repository import require_match
from matchmind.api.schemas import Counterfactual
from matchmind.models.gamestate_model import anchor_features, intervene, predict


def change_for(marker: dict) -> str | None:
    if marker["type"] == "goal":
        return "remove_goal"
    if marker["type"] == "sub":
        return "no_sub"
    if marker["type"] == "card" and marker["detail"] in ("red", "second_yellow"):
        return "remove_red_card"
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8020")
    parser.add_argument(
        "--output", type=Path, default=Path("/tmp/matchmind-whatif-sweep.json")
    )
    args = parser.parse_args()
    records, sanity, failures = [], [], []
    with httpx.Client(base_url=args.url, timeout=90) as client:
        matches = client.get("/api/matches").raise_for_status().json()["matches"]
        selected = random.Random(2026).sample(
            sorted(matches, key=lambda m: m["match_id"]), 20
        )
        # The first counterfactual request includes cold model/index initialization.
        for match in selected:
            mid = match["match_id"]
            markers = (
                client.get(f"/api/matches/{mid}").raise_for_status().json()["markers"]
            )
            for marker in markers:
                change = change_for(marker)
                if not change:
                    continue
                started = time.perf_counter()
                response = client.post(
                    f"/api/matches/{mid}/counterfactual",
                    json={"event_id": marker["event_id"], "change": change},
                )
                elapsed = (time.perf_counter() - started) * 1000
                record = {
                    "match_id": mid,
                    "event_id": marker["event_id"],
                    "change": change,
                    "status": response.status_code,
                    "ms": elapsed,
                }
                try:
                    response.raise_for_status()
                    result = response.json()
                    Counterfactual.model_validate(result)
                    assert result["method"] == "trained_model"
                    assert result["n_analogs"] == result["analog_summary"]["n"] == 40
                    assert all(
                        a["match_id"] != mid and 0 <= a["similarity"] <= 1
                        for a in result["analogs"]
                    )
                    assert all(p["modelled"] is None for p in result["series"])
                    for side in ("home", "away"):
                        for metric in ("xg", "possession"):
                            b = result["modelled"][side][metric]
                            assert 0 <= b["p10"] <= b["p50"] <= b["p90"]
                            if metric == "possession":
                                assert b["p90"] <= 1
                    record["non_demo_analogs"] = sum(
                        a["match_id"] not in {m["match_id"] for m in matches}
                        for a in result["analogs"]
                    )
                except Exception as exc:
                    record["error"] = str(exc)
                    failures.append(record)
                records.append(record)
            print(mid, "complete", flush=True)
        final = "sb:3869685"
        markers = (
            client.get(f"/api/matches/{final}").raise_for_status().json()["markers"]
        )
        chosen = [
            next(m for m in markers if m["type"] == "goal" and m["minute"] == 79),
            next(m for m in markers if m["type"] == "goal" and m["minute"] == 107),
            next(m for m in markers if m["type"] == "sub"),
        ]
        actions, context = inference_inputs(final)
        for marker in chosen:
            anchor = {**context["anchors"][marker["event_id"]], "team": marker["team"]}
            factual = anchor_features(actions, context, anchor, require_match(final))
            changed = intervene(factual, anchor, context, change_for(marker))
            factual_prediction = predict(factual)
            result = (
                client.post(
                    f"/api/matches/{final}/counterfactual",
                    json={"event_id": marker["event_id"], "change": change_for(marker)},
                )
                .raise_for_status()
                .json()
            )
            sanity.append(
                {
                    "event_id": marker["event_id"],
                    "anchor": result["anchor"],
                    "change": change_for(marker),
                    "team": marker["team"],
                    "factual_features": factual.to_dict("records"),
                    "changed_features": changed.to_dict("records"),
                    "factual": {
                        side: {
                            metric: {
                                q: v[i] for q, v in factual_prediction[target].items()
                            }
                            for metric, target in (
                                ("xg", "xg_for"),
                                ("possession", "possession_share"),
                            )
                        }
                        for i, side in enumerate(("home", "away"))
                    },
                    "counterfactual": result["modelled"],
                }
            )
    latencies = [r["ms"] for r in records]
    index = training_analogs()
    report = {
        "seed": 2026,
        "matches": [m["match_id"] for m in selected],
        "requests": len(records),
        "changes": dict(Counter(r["change"] for r in records)),
        "failures": failures,
        "latency_ms": {
            "p50": float(np.quantile(latencies, 0.5)),
            "p95": float(np.quantile(latencies, 0.95)),
            "max": max(latencies),
            "first_cold": latencies[0],
        },
        "training_matches": int(index.windows.match_id.nunique()),
        "eligible_windows": len(index.windows),
        "non_demo_analog_appearances": sum(
            r.get("non_demo_analogs", 0) for r in records
        ),
        "sanity": sanity,
        "records": records,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in ("sanity", "records")},
            indent=2,
        )
    )
    print("Evidence:", args.output)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
