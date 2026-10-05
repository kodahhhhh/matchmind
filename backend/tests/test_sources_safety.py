"""Identity ambiguity, archive boundaries and unavailable model context."""

import json
import stat
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from matchpulse.sources.acquire import extract_archive
from matchpulse.sources.identities import select_player
from matchpulse.sources.inference import Inference
from matchpulse.sources.lite import enrich_understat
from matchpulse.sources.pipeline import rebuild_understat, refresh


def test_player_alias_requires_unique_team_evidence() -> None:
    aliases = {"alex smith": {1, 2}}
    assert select_player("Alex Smith", {1}, aliases) == 1
    assert select_player("Alex Smith", {1, 2}, aliases) is None
    assert select_player("Alex Smith", {3}, aliases) is None
    assert select_player("Alex Smit", {1}, aliases) is None


def test_archive_is_idempotent_and_rejects_escape(tmp_path: Path) -> None:
    archive = tmp_path / "raw.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("Datasets/match/match.json", "{}")
        zipped.writestr("Datasets/match/events.jsonl", "{}")
    root = tmp_path / "extracted"
    assert extract_archive(archive, root) == 2
    assert extract_archive(archive, root) == 0
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("../match.json", "{}")
    with pytest.raises(ValueError, match="Unsafe archive path"):
        extract_archive(archive, root)
    with zipfile.ZipFile(archive, "w") as zipped:
        member = zipfile.ZipInfo("Datasets/alias/match.json")
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        zipped.writestr(member, "/outside")
    with pytest.raises(ValueError, match="symlinks"):
        extract_archive(archive, root)


def test_lite_inference_keeps_unobserved_context_missing() -> None:
    captured = []

    class Model:
        def predict(self, frame: object, *, num_threads: int) -> np.ndarray:
            captured.append(frame)
            return np.array([0.1, 0.2])

    inference = Inference.__new__(Inference)
    inference.models = {"xg": Model()}
    match = {"data_tier": "lite", "home": {"id": 1}, "away": {"id": 2}}
    event = {
        "id": "us:1:0",
        "team": {"id": 1},
        "period": 1,
        "minute": 10,
        "location": [110, 40],
        "type": {"name": "Shot"},
        "shot": {
            "body_part": {"name": "Other"},
            "type": {"name": "Other"},
            "outcome": {"name": "Goal"},
        },
    }
    inference.shots(match, [event, {**event, "id": "us:1:1"}])
    features = captured[0]
    assert (
        features[["score_diff", "body_part", "shot_type", "set_piece"]]
        .isna()
        .all()
        .all()
    )
    assert (
        features[["first_time", "under_pressure", "opponents_in_cone"]]
        .isna()
        .all()
        .all()
    )
    assert features["x"].notna().all()


def test_provider_stats_require_exact_team_date_and_side() -> None:
    fixture = {"h": {"id": "1"}, "a": {"id": "2"}, "datetime": "2026-09-01 12:00:00"}
    row = {"date": fixture["datetime"], "h_a": "h", "ppda": {"att": 10, "def": 1}}
    discovery = {"teams": {"1": {"history": [row]}, "2": {"history": [row]}}}
    result = enrich_understat({"capabilities": {}}, fixture, discovery)
    assert result["provider_team_stats"] == {"home": row, "away": None}


def test_cached_rebuild_has_no_network_dependency(tmp_path: Path) -> None:
    fixture = {
        "id": "1",
        "isResult": True,
        "datetime": "2026-09-01 12:00:00",
        "h": {"id": "10", "title": "Home"},
        "a": {"id": "20", "title": "Away"},
        "goals": {"h": "0", "a": "0"},
    }
    details = {"shots": {"h": [], "a": []}, "rosters": {"h": {}, "a": {}}}
    root = tmp_path / "raw/understat"
    root.mkdir(parents=True)
    discovery = root / "discovery.body"
    discovery.write_text(json.dumps({"dates": [fixture]}))
    discovery.with_suffix(".json").write_text(
        json.dumps(
            {
                "url": "https://understat.com/getLeagueData/EPL/2026?mp_snapshot=2026-10-05",
                "status": 200,
                "fetched_at": 1,
            }
        )
    )
    detail = root / "detail.body"
    detail.write_text(json.dumps(details))

    class Cache:
        def fetch(self, source: str, url: str, *, ajax: bool) -> Path:
            return detail if "getMatchData" in url else discovery

    class Predictor:
        def shots(self, match: dict, events: list[dict]) -> dict:
            return {}

    refresh(
        tmp_path,
        Cache(),
        Predictor(),
        seasons=[2026],
        leagues=["EPL"],
        snapshot=date(2026, 10, 5),
    )
    assert rebuild_understat(tmp_path, Predictor()) == {
        "rebuilt": 1,
        "network_requests": 0,
    }
