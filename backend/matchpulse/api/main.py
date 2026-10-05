"""MatchPulse API. Launch with uvicorn matchpulse.api.main:app."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from matchpulse.api.repository import connect
from matchpulse.api.routes.ask import router as ask_router
from matchpulse.api.routes.backtest import router as backtest_router
from matchpulse.api.routes.counterfactual import router as counterfactual_router
from matchpulse.api.routes.matches import router as matches_router
from matchpulse.api.routes.players import router as players_router
from matchpulse.api.routes.search import router as search_router

app = FastAPI(title="MatchPulse", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)
app.include_router(backtest_router, prefix="/api")
app.include_router(players_router, prefix="/api")
app.include_router(matches_router, prefix="/api")
app.include_router(counterfactual_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(ask_router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    with connect() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


# Production: serve the built frontend (frontend/dist) from the same origin as the API.
DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        """Static file if it exists, otherwise the SPA shell (client-side routes)."""
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        target = (DIST / path).resolve()
        if path and target.is_file() and DIST.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
