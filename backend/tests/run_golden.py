"""Live golden transcripts; numerics and citations validated against tool outputs."""

import asyncio
import json
import time
from pathlib import Path

from pydantic import TypeAdapter

from matchmind.analyst.agent import ask_chunks
from matchmind.analyst.grounding import CITATION, grounding_errors
from matchmind.analyst.tools import citation_registry
from matchmind.api.repository import bundle, catalogue
from matchmind.api.schemas import AskChunk

QUESTIONS = [
    "Find the turning point",
    "Who was actually progressing the ball?",
    "Show me the three most dangerous sequences",
    "What changed after the substitutions?",
]


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
        registry = citation_registry(bundle("sb:3869685"))
        # Cross-match search citations also need to resolve to a loaded real sequence.
        for kind, ref in CITATION.findall(audit["text"]):
            key = f"{kind}:{ref}"
            if key not in registry:
                mid = ":".join(ref.split(":")[:2])
                assert mid in catalogue()
                assert key in citation_registry(bundle(mid))
        assert chunks[-1] == {"type": "done"}
        assert audit["tools"], audit["text"]
        assert CITATION.findall(audit["text"]), audit["text"]
        assert not any(errors.values()), errors
        assert not audit["rejections"], audit["rejections"]
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
