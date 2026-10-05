"""Recheck saved live Sol transcripts against their own results and real IDs."""

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from matchpulse.analyst.grounding import CITATION, grounding_errors
from matchpulse.analyst.tools import citation_exists
from matchpulse.api.repository import bundle
from matchpulse.api.schemas import AskChunk


@pytest.mark.parametrize("name", [f"{i:02d}" for i in range(1, 11)])
def test_live_golden_transcript_is_grounded(name: str) -> None:
    record = json.loads(
        (Path(__file__).with_name("golden") / (name + ".json")).read_text()
    )
    results = [t["result"] for t in record["tools"]]
    errors = grounding_errors(record["text"], results)
    assert not any(errors.values()), errors
    assert record["rejections"] == []
    assert record["all_citations_exist"]
    assert record["chunks"][-1] == {"type": "done"}
    for kind, ref in CITATION.findall(record["text"]):
        mid = ":".join(ref.split(":")[:2])
        assert citation_exists(kind, ref, bundle(mid)), (kind, ref)
    adapter = TypeAdapter(AskChunk)
    for chunk in record["chunks"]:
        adapter.validate_python(chunk)
