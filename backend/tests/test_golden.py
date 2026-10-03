"""Recheck saved live Sol transcripts against their own results and real IDs."""

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from matchmind.analyst.grounding import CITATION, grounding_errors
from matchmind.analyst.tools import citation_registry
from matchmind.api.repository import bundle
from matchmind.api.schemas import AskChunk


@pytest.mark.parametrize("name", ["01", "02", "03", "04"])
def test_live_golden_transcript_is_grounded(name: str) -> None:
    record = json.loads(
        (Path(__file__).with_name("golden") / (name + ".json")).read_text()
    )
    results = [t["result"] for t in record["tools"]]
    errors = grounding_errors(record["text"], results)
    assert errors == {"unsupported_numbers": [], "unsupported_citations": []}
    assert record["rejections"] == []
    assert record["all_citations_exist"]
    assert record["chunks"][-1] == {"type": "done"}
    registry = citation_registry(bundle(record["match_id"]))
    for kind, ref in CITATION.findall(record["text"]):
        assert f"{kind}:{ref}" in registry
    adapter = TypeAdapter(AskChunk)
    for chunk in record["chunks"]:
        adapter.validate_python(chunk)
