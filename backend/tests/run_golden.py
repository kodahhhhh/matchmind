"""Live golden transcripts; numerics and citations validated against tool outputs."""

import asyncio
import json
import time
from pathlib import Path

from pydantic import TypeAdapter

from matchpulse.analyst.agent import ask_chunks
from matchpulse.analyst.grounding import CITATION, grounding_errors
from matchpulse.analyst.tools import citation_exists
from matchpulse.api.repository import bundle, catalogue
from matchpulse.api.schemas import AskChunk

QUESTIONS = [
    "Find the turning point",
    "Who was actually progressing the ball?",
    "Show me the three most dangerous sequences",
    "What changed after the substitutions?",
    "Why did Argentina lose control between the 65th and 85th minute?",
    "What happened around the first goal?",
    "What if Mbappé's 80th-minute penalty had been missed?",
    "What if France hadn't made their double substitution before half-time?",
    "Should Kolo Muani have passed instead of shooting at the end of extra time?",
    "Who was Argentina's most valuable player, and why?",
]
WHAT_IF_TOOLS = {
    7: "run_counterfactual",
    8: "run_counterfactual",
    9: "shot_alternatives",
}


async def main() -> None:
    directory = Path(__file__).with_name("golden")
    directory.mkdir(exist_ok=True)
    summary = []
    for i, question in enumerate(QUESTIONS, 1):
        audit = {}
        chunks = []
        start = time.monotonic()
        first = None
        async for chunk in ask_chunks("sb:3869685", question, [], audit):
            TypeAdapter(AskChunk).validate_python(chunk)
            if chunk["type"] == "text" and first is None:
                first = round(time.monotonic() - start, 3)
            chunks.append(chunk)
        results = [t["result"] for t in audit["tools"]]
        errors = grounding_errors(audit["text"], results)
        # Citations must resolve to a real event, marker or sequence, including
        # cross-match search results and short sequences outside the top list.
        for kind, ref in CITATION.findall(audit["text"]):
            mid = ":".join(ref.split(":")[:2])
            assert mid in catalogue()
            assert citation_exists(kind, ref, bundle(mid)), (kind, ref)
        assert chunks[-1] == {"type": "done"}
        assert audit["tools"], audit["text"]
        assert CITATION.findall(audit["text"]), audit["text"]
        assert not any(errors.values()), errors
        assert not audit["rejections"], audit["rejections"]
        if i in WHAT_IF_TOOLS:
            assert WHAT_IF_TOOLS[i] in [t["name"] for t in audit["tools"]]
        audit.update(
            {
                "chunks": chunks,
                "first_text_seconds": first,
                "total_seconds": round(time.monotonic() - start, 3),
                "grounding": errors,
                "all_citations_exist": True,
            }
        )
        (directory / f"{i:02d}.json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
        )
        summary.append(
            {
                "question": question,
                "tools": [t["name"] for t in audit["tools"]],
                "first_text_seconds": first,
                "grounding": errors,
                "all_citations_exist": True,
            }
        )
        print(question, first, audit["text"], flush=True)
    (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
