"""Bounded Responses tool loop with sentence-level evidence validation and SSE."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from matchmind.analyst.client import async_client
from matchmind.analyst.grounding import (
    CITATION,
    grounding_errors,
    sentences,
    text_deltas,
)
from matchmind.analyst.prompts import SYSTEM, match_summary
from matchmind.analyst.tools import TOOLS, citation_registry, dispatch
from matchmind.api.repository import bundle
from matchmind.config import get_settings


async def ask_chunks(
    match_id: str, question: str, history: list[dict], audit: dict | None = None
) -> AsyncIterator[dict[str, Any]]:
    """Stream only grounded sentences; provider/tool failures always finish with done.

    `audit` records tool outputs for golden validation without changing SSE shapes.
    No user transcript is stored by production requests.
    """
    results = []
    answer = []
    cited = set()
    if audit is None:
        audit = {}
    audit.update(
        {
            "match_id": match_id,
            "question": question,
            "tools": [],
            "text": "",
            "rejections": [],
        }
    )
    try:
        b = await asyncio.to_thread(bundle, match_id)
        registry = citation_registry(b)
        inputs = [
            {"role": "system", "content": SYSTEM + "\n" + match_summary(b["match"])},
            *history,
            {"role": "user", "content": question},
        ]
        emitted = False
        async with asyncio.timeout(180):
            for turn in range(7):
                response = None
                buffer = ""
                calls = []
                stream = await async_client().responses.create(
                    model=get_settings().analyst_model,
                    input=inputs,
                    tools=TOOLS,
                    tool_choice="required" if turn == 0 else "auto",
                    stream=True,
                    store=False,
                    reasoning={"effort": "low"},
                    text={"verbosity": "low"},
                    max_output_tokens=3500,
                )
                try:
                    async for event in stream:
                        if event.type == "response.output_text.delta":
                            buffer += event.delta
                            parts, buffer = sentences(buffer)
                            for part in parts:
                                errors = grounding_errors(part, results)
                                if any(errors.values()):
                                    audit["rejections"].append({"text": part, **errors})
                                    continue
                                for delta in text_deltas(part):
                                    answer.append(delta)
                                    emitted = True
                                    yield {"type": "text", "delta": delta}
                        elif (
                            event.type == "response.output_item.done"
                            and event.item.type == "function_call"
                        ):
                            calls.append(event.item)
                        elif event.type == "response.completed":
                            response = event.response
                        elif event.type in (
                            "response.failed",
                            "error",
                            "response.incomplete",
                        ):
                            raise RuntimeError("Analyst response did not complete")
                finally:
                    await stream.close()
                if buffer:
                    errors = grounding_errors(buffer, results)
                    if any(errors.values()):
                        audit["rejections"].append({"text": buffer, **errors})
                    else:
                        for delta in text_deltas(buffer):
                            answer.append(delta)
                            emitted = True
                            yield {"type": "text", "delta": delta}
                if response is None:
                    raise RuntimeError("Missing analyst response")
                if not calls:
                    break
                inputs.extend(
                    item.model_dump(exclude_none=True) for item in response.output
                )
                for call in calls:
                    args = json.loads(call.arguments)
                    yield {"type": "tool", "name": call.name, "args": args}
                    try:
                        result = await dispatch(match_id, call.name, args)
                    except Exception:
                        result = {
                            "error": (
                                "The requested calculation is unavailable. "
                                "Try another tool."
                            )
                        }
                    results.append(result)
                    audit["tools"].append(
                        {"name": call.name, "args": args, "result": result}
                    )
                    inputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps(result, ensure_ascii=False),
                        }
                    )
            text = "".join(answer)
            for kind, ref in CITATION.findall(text):
                token = f"{kind}:{ref}"
                if token in cited:
                    continue
                label = registry.get(token)
                if label is None:
                    label = next(
                        (
                            r.get("evidence_labels", {}).get(token)
                            for r in results
                            if token in r.get("evidence_labels", {})
                        ),
                        None,
                    )
                if label:
                    cited.add(token)
                    yield {"type": "citation", "ref": token, "label": label}
            if not emitted:
                text = (
                    "I could not verify an answer from the available match evidence. "
                    "Try a narrower question."
                )
                answer.append(text)
                yield {"type": "text", "delta": text}
    except asyncio.CancelledError:
        raise
    except Exception:
        text = "The analyst could not finish this request. Please try again."
        answer.append(text)
        yield {"type": "text", "delta": text}
    finally:
        audit["text"] = "".join(answer)
    yield {"type": "done"}
