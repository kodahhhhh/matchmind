"""MatchMind API. Launch with uvicorn matchmind.api.main:app."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from matchmind.api.repository import connect
from matchmind.api.routes.matches import router as matches_router

app = FastAPI(title="MatchMind", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)
app.include_router(matches_router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    with connect() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}
