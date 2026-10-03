"""Explicit full-corpus HTTP sweep and latency report (run with API on :8000)."""

import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
import pandas as pd

from matchmind.api.repository import catalogue, connect
from matchmind.api.schemas import Counterfactual

ENDPOINTS = (
    "",
    "/events",
    "/timeline",
    "/sequences?sort=danger&limit=5",
    "/players",
    "/turning-points",
)
REPORT = Path(__file__).with_name("golden") / "verification.json"


def main() -> None:
    start = time.monotonic()
    failures = []
    latencies = {e or "/match": [] for e in ENDPOINTS}
    latencies["/search"] = []
    with httpx.Client(
        base_url="http://127.0.0.1:8000/api",
        timeout=60,
        limits=httpx.Limits(max_connections=16),
    ) as client:
        for path in ("/health", "/competitions", "/matches"):
            r = client.get(path)
            r.raise_for_status()
        cards = client.get("/matches").json()["matches"]
        assert len(cards) == 493
        cats = catalogue()
        euros = [c["match_id"] for c in cards if c["competition"] == "UEFA Euro"]
        rebuilt = [c["match_id"] for c in cards if c["reconstructed"]]
        mls = [
            c["match_id"] for c in cards if c["competition"] == "Major League Soccer"
        ]
        with connect() as conn:
            red = conn.execute(
                "SELECT e.match_id,e.event_id FROM events e "
                "JOIN matches m USING(match_id) "
                "WHERE (m.meta->>'demo')::boolean AND e.period<5 AND "
                "(e.extra->'foul_committed'->'card'->>'name' "
                "IN ('Red Card','Second Yellow') OR "
                "e.extra->'bad_behaviour'->'card'->>'name' "
                "IN ('Red Card','Second Yellow')) LIMIT 1"
            ).fetchone()
        smoke = list(
            dict.fromkeys(
                [
                    "sb:3869685",
                    euros[-1],
                    rebuilt[0],
                    *mls,
                    *([red["match_id"]] if red else []),
                ]
            )
        )

        def sweep(mid: str) -> dict:
            problems = []
            times = {}
            for endpoint in ENDPOINTS:
                now = time.perf_counter()
                try:
                    r = client.get("/matches/" + mid + endpoint)
                    if r.status_code != 200:
                        problems.append(
                            {
                                "match_id": mid,
                                "endpoint": endpoint,
                                "status": r.status_code,
                                "body": r.text[:300],
                            }
                        )
                    else:
                        result = r.json()
                        if endpoint == "":
                            assert result["match_id"] == mid
                            assert result["match_date"] == cats[mid]["match_date"]
                        elif endpoint == "/events":
                            es = result["events"]
                            assert es and all(e["period"] < 5 for e in es)
                            assert len({e["id"] for e in es}) == len(es)
                            assert [e["t"] for e in es] == sorted(e["t"] for e in es)
                        elif endpoint == "/timeline":
                            rows = result["minutes"]
                            assert rows
                            assert [r["index"] for r in rows] == list(range(len(rows)))
                        elif endpoint == "/turning-points":
                            assert len(result["turning_points"]) <= 3
                except Exception as exc:
                    problems.append(
                        {"match_id": mid, "endpoint": endpoint, "error": str(exc)[:300]}
                    )
                times[endpoint or "/match"] = (time.perf_counter() - now) * 1000
            now = time.perf_counter()
            try:
                r = client.get(
                    "/search", params={"q": "dangerous left attacks", "match_id": mid}
                )
                r.raise_for_status()
                assert r.json()["query"] == "dangerous left attacks"
            except Exception as exc:
                problems.append(
                    {"match_id": mid, "endpoint": "/search", "error": str(exc)[:300]}
                )
            times["/search"] = (time.perf_counter() - now) * 1000
            return {"match_id": mid, "failures": problems, "times": times}

        smoke_results = [sweep(mid) for mid in smoke]
        if red:
            r = client.post(
                "/matches/" + red["match_id"] + "/counterfactual",
                json={"event_id": red["event_id"], "change": "remove_red_card"},
            )
            assert r.status_code == 200, r.text
            Counterfactual.model_validate(r.json())
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(sweep, c["match_id"]) for c in cards]
            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                failures.extend(result["failures"])
                for endpoint, ms in result["times"].items():
                    if endpoint != "/match":
                        latencies[endpoint].append(ms)
                if i % 25 == 0:
                    print(f"HTTP sweep: {i}/493, {len(failures)} failures", flush=True)
        # Controlled warm sample, no corpus loading in parallel.
        warm = {}
        for endpoint in ENDPOINTS:
            client.get("/matches/sb:3869685" + endpoint).raise_for_status()
            measurements = []
            for _ in range(20):
                now = time.perf_counter()
                client.get("/matches/sb:3869685" + endpoint).raise_for_status()
                measurements.append((time.perf_counter() - now) * 1000)
            warm[endpoint or "/match"] = {
                "median_ms": round(statistics.median(measurements), 2),
                "p95_ms": round(float(pd.Series(measurements).quantile(0.95)), 2),
                "max_ms": round(max(measurements), 2),
            }
        for endpoint in (
            "/competitions",
            "/matches",
            "/search?q=dangerous&match_id=sb:3869685",
            "/health",
        ):
            measurements = []
            for _ in range(20):
                now = time.perf_counter()
                client.get(endpoint).raise_for_status()
                measurements.append((time.perf_counter() - now) * 1000)
            warm[endpoint.split("?")[0]] = {
                "median_ms": round(statistics.median(measurements), 2),
                "p95_ms": round(float(pd.Series(measurements).quantile(0.95)), 2),
                "max_ms": round(max(measurements), 2),
            }
        first_text = None
        now = time.monotonic()
        chunks = []
        with client.stream(
            "POST",
            "/matches/sb:3869685/ask",
            json={"question": "Find the turning point", "history": []},
            timeout=200,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue
                chunk = json.loads(line[6:])
                chunks.append(chunk)
                if chunk["type"] == "text" and first_text is None:
                    first_text = round(time.monotonic() - now, 3)
        assert chunks[-1] == {"type": "done"}
        report = {
            "matches": 493,
            "get_requests": 493 * 7,
            "failures": failures,
            "smoke_matches": smoke_results,
            "red_card_match": red,
            "warm_latency": warm,
            "ask_first_text_seconds": first_text,
            "ask_http_chunks": chunks,
            "sweep_seconds": round(time.monotonic() - start, 2),
        }
        REPORT.parent.mkdir(exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(
            json.dumps(
                {
                    k: v
                    for k, v in report.items()
                    if k not in ("smoke_matches", "ask_http_chunks")
                },
                indent=2,
            )
        )
        assert not failures


if __name__ == "__main__":
    main()
