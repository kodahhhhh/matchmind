"""Read-only inference using the current xG/VAEP/xT model stack."""

import json
import warnings
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from socceraction.spadl import play_left_to_right
from socceraction.vaep import VAEP
from socceraction.vaep.features import goalscore
from socceraction.vaep.formula import value
from socceraction.xthreat import ExpectedThreat

from matchpulse.models.xg import FEATURES, shot_features


class Inference:
    """Load existing artifacts once. Never train or write into data/models."""

    def __init__(self, model_dir: Path) -> None:
        self.models = {
            n: lgb.Booster(model_file=str(model_dir / f"{n}.txt"))
            for n in ("xg", "vaep_scores", "vaep_concedes")
        }
        self.features = json.loads((model_dir / "vaep.json").read_text())["features"]
        self.xt = ExpectedThreat(l=12, w=8)
        self.xt.xT = np.asarray(json.loads((model_dir / "xt.json").read_text())["grid"])

    def shots(self, match: dict, events: list[dict]) -> dict[str, float]:
        """Our xG only; source xG remains separate validation/provenance metadata.

        Unobserved context is missing, not fabricated false. This transfer is not
        validated on youth/lite providers and must be labelled as such.
        """
        score = {match[s]["id"]: 0 for s in ("home", "away")}
        rows, ids = [], []
        for event in events:
            team = event["team"]["id"]
            other = next(t for t in score if t != team)
            if event["type"]["name"] == "Shot" and event.get("location"):
                row = shot_features(event)
                row["score_diff"] = score[team] - score[other]
                if match.get("data_tier") == "lite":
                    # Minute-only order is insufficient for exact pre-shot score.
                    row["score_diff"] = np.nan
                for column in (
                    "first_time",
                    "under_pressure",
                    "through_ball",
                    "cross",
                    "cut_back",
                    "opponents_in_cone",
                    "keeper_present",
                    "technique",
                ):
                    row[column] = np.nan
                if event["shot"].get("body_part", {}).get("name") == "Other":
                    row["body_part"] = np.nan
                if event["shot"].get("type", {}).get("name") == "Other":
                    row["shot_type"] = np.nan
                    row["set_piece"] = np.nan
                rows.append(row)
                ids.append(event["id"])
                if event["period"] < 5 and event["shot"]["outcome"]["name"] == "Goal":
                    score[team] += 1
            elif event["type"]["name"] == "Own Goal Against":
                score[other] += 1
        if not rows:
            return {}
        prediction = self.models["xg"].predict(
            pd.DataFrame(rows)[FEATURES], num_threads=1
        )
        return dict(zip(ids, map(float, prediction), strict=True))

    def score(
        self, match: dict, actions: pd.DataFrame, events: list[dict]
    ) -> pd.DataFrame:
        """Same period resets, goalscore context and VAEP formula as existing stack."""
        result = actions.copy()
        xg = self.shots(match, events)
        result["xg"] = result.original_event_id.map(xg)
        score_context = goalscore([actions]).set_index(actions.action_id)
        # Wyscout can encode an own goal as a bad touch, outside socceraction's
        # shot-only goalscore helper. Use the observed normalized goal stream.
        if any(e["type"]["name"] == "Own Goal Against" for e in events):
            scores = {match[s]["id"]: 0 for s in ("home", "away")}
            contexts = {}
            for event in events:
                team = event["team"]["id"]
                other = next(t for t in scores if t != team)
                contexts[event["id"]] = (scores[team], scores[other])
                if event["type"]["name"] == "Own Goal Against":
                    scores[other] += 1
                elif (
                    event["type"]["name"] == "Shot"
                    and event["shot"]["outcome"]["name"] == "Goal"
                ):
                    scores[team] += 1
            for action in actions.itertuples():
                a, b = contexts[action.original_event_id]
                score_context.loc[action.action_id] = [a, b, a - b]
        vaep = VAEP(nb_prev_actions=3)
        outputs = []
        for _, group in actions.groupby("period_id", sort=False):
            group = group.reset_index(drop=True)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                features = vaep.compute_features(
                    pd.Series({"home_team_id": match["home"]["id"]}), group
                ).astype("float32")
            for column in score_context:
                features[column] = score_context.loc[group.action_id, column].to_numpy(
                    dtype="float32"
                )
            predictions = {
                t: self.models[f"vaep_{t}"].predict(
                    features[self.features], num_threads=1
                )
                for t in ("scores", "concedes")
            }
            values = value(
                group,
                pd.Series(predictions["scores"]),
                pd.Series(predictions["concedes"]),
            )
            values["action_id"] = group.action_id
            outputs.append(values)
        ratings = pd.concat(outputs).set_index("action_id")
        for column in ("offensive_value", "defensive_value", "vaep_value"):
            result[column] = result.action_id.map(ratings[column])
        result["xt"] = self.xt.rate(play_left_to_right(actions, match["home"]["id"]))
        return result
