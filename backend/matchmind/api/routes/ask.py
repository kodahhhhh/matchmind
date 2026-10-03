"""Frontend AskChunk SSE boundary, with no buffering or raw provider exceptions."""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from matchmind.analyst.agent import ask_chunks
from matchmind.api.repository import require_match
from matchmind.api.schemas import AskRequest

router = APIRouter()


@router.post("/matches/{match_id}/ask")
def ask(match_id: str, request: AskRequest) -> StreamingResponse:
    require_match(match_id)

    async def frames():
        async for chunk in ask_chunks(
            match_id, request.question, [h.model_dump() for h in request.history]
        ):
            yield "data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n"

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
