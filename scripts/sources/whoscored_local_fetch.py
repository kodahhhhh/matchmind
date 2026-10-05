# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright==1.58.0", "json5>=0.12,<1"]
# ///
"""Owner-run genuine Chromium capture, immutable caches and Tailscale rsync.

No stealth settings, proxy network, automatic CAPTCHA solution or request signing.
The browser may resolve its own JS challenge; a remaining refusal stops the job.
"""

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import json5
from playwright.async_api import async_playwright

BASE = "https://www.whoscored.com"
LEAGUES = {
    "Premier League": (252, 2, "England"),
    "La Liga": (206, 4, "Spain"),
    "Serie A": (108, 5, "Italy"),
    "1. Bundesliga": (81, 3, "Germany"),
    "Ligue 1": (74, 22, "France"),
    "Champions League": (250, 12, "International"),
}
TARGET = "ubuntu@100.97.212.47:~/hackathon/data/raw/whoscored/"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def embedded(text: str, variable: str) -> object | None:
    """Parse a balanced JSON/JSON5 object without executing captured JS."""
    for match in re.finditer(r"\b" + re.escape(variable) + r"\s*[:=]\s*", text):
        start = match.end()
        if text[start : start + 1] not in ("{", "["):
            continue
        depth, quote, escaped = 0, None, False
        for end in range(start, len(text)):
            c = text[end]
            if quote:
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif c == quote:
                    quote = None
            elif c in ('"', "'"):
                quote = c
            elif c in "{[":
                depth += 1
            elif c in "}]":
                depth -= 1
                if depth == 0:
                    try:
                        return json5.loads(text[start : end + 1])
                    except ValueError:
                        break
    return None


class BrowserCache:
    """Replay complete cached responses and pace new JSON/page requests."""

    def __init__(self, root: Path, budget_gb: float = 10) -> None:
        self.root = root
        self.responses = root / "responses"
        self.pages = root / "pages"
        self.responses.mkdir(parents=True, exist_ok=True)
        self.pages.mkdir(exist_ok=True)
        self.bytes = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
        self.budget = int(budget_gb * 1024**3)
        self.last = {}
        self.locks = {}
        self.pending = set()
        self.navigation_status = {}

    async def pace(self, host: str, seconds: float) -> None:
        async with self.locks.setdefault(host, asyncio.Lock()):
            delay = seconds - (time.time() - self.last.get(host, 0))
            if delay > 0:
                await asyncio.sleep(delay)
            self.last[host] = time.time()

    def key(self, request: object) -> str:
        return hashlib.sha256(
            (
                request.method + " " + request.url + " " + (request.post_data or "")
            ).encode()
        ).hexdigest()

    async def route(self, route: object, request: object) -> None:
        key = self.key(request)
        meta = self.responses / f"{key}.json"
        body = self.responses / f"{key}.body"
        if meta.exists() and body.exists():
            record = json.loads(meta.read_text())
            if record.get("complete"):
                await route.fulfill(
                    status=record["status"],
                    headers=record["headers"],
                    body=body.read_bytes(),
                )
                return
        if self.bytes >= self.budget:
            await route.abort()
            return
        if request.is_navigation_request() or request.resource_type in ("xhr", "fetch"):
            await self.pace(
                urlparse(request.url).netloc,
                3.1 if request.is_navigation_request() else 1.1,
            )
        await route.continue_()

    async def response(self, response: object) -> None:
        key = self.key(response.request)
        meta = self.responses / f"{key}.json"
        body = self.responses / f"{key}.body"
        if meta.exists() and json.loads(meta.read_text()).get("complete"):
            return
        error = None
        try:
            data = await response.body()
        except Exception as exc:
            data = b""
            error = str(exc)[:250]
        if self.bytes + len(data) > self.budget:
            raise RuntimeError("Raw cache budget reached")
        body.write_bytes(data)
        self.bytes += len(data)
        headers = {
            k: v
            for k, v in (await response.all_headers()).items()
            if k in ("content-type", "location", "cache-control")
        }
        write_json(
            meta,
            {
                "url": response.url,
                "method": response.request.method,
                "status": response.status,
                "headers": headers,
                "bytes": len(data),
                "fetched_at": time.time(),
                "complete": error is None
                or response.status in (301, 302, 303, 307, 308),
                "error": error,
            },
        )

    def on_response(self, response: object) -> None:
        if response.request.is_navigation_request():
            self.navigation_status[response.url] = response.status
        task = asyncio.create_task(self.response(response))
        self.pending.add(task)
        # Keep tasks until drained so response-body/cache errors are surfaced.

    async def drain(self) -> None:
        tasks = list(self.pending)
        self.pending.clear()
        if tasks:
            await asyncio.gather(*tasks)

    async def open(self, page: object, url: str, wait: float) -> str:
        key = hashlib.sha256(url.encode()).hexdigest()
        snapshot = self.pages / f"{key}.html"
        meta = self.pages / f"{key}.json"
        if snapshot.exists():
            record = json.loads(meta.read_text())
            if record.get("blocked"):
                raise RuntimeError(f"Cached page refusal: {url}")
            return snapshot.read_text()
        response = await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(wait * 1000)
        html = await page.content()
        initial_status = response.status if response else None
        status = self.navigation_status.get(page.url, initial_status)
        title = await page.title()
        blocked = status in (403, 429) or any(
            x in (title + " " + html[:200000]).lower()
            for x in (
                "attention required",
                "just a moment",
                "verify you are human",
                "captcha.html",
                "cf-chl-",
            )
        )
        if self.bytes + len(html.encode()) > self.budget:
            raise RuntimeError("Raw cache budget reached before saving rendered page")
        snapshot.write_text(html)
        self.bytes += len(html.encode())
        write_json(
            meta,
            {
                "url": url,
                "final_url": page.url,
                "status": status,
                "initial_status": initial_status,
                "title": title,
                "blocked": blocked,
            },
        )
        await self.drain()
        if blocked:
            raise RuntimeError(
                f"Browser refused access: HTTP {status}, {title}. "
                "No automatic CAPTCHA solution is used."
            )
        if status is not None and status >= 400:
            raise RuntimeError(f"Page HTTP {status}: {url}")
        return html


async def options(
    page: object, cache: BrowserCache, html: str, needle: str
) -> list[dict]:
    """Read cached HTML options as data without replaying page scripts."""
    from html.parser import HTMLParser

    class Selects(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.active = False
            self.option = None
            self.items = []

        def handle_starttag(self, tag: str, attrs: list) -> None:
            a = dict(attrs)
            if tag == "select":
                self.active = needle in a.get("id", "").lower()
            if tag == "option" and self.active:
                self.option = {"url": a.get("value", ""), "text": ""}

        def handle_data(self, data: str) -> None:
            if self.option is not None:
                self.option["text"] += data

        def handle_endtag(self, tag: str) -> None:
            if tag == "option" and self.option is not None:
                self.items.append(self.option)
                self.option = None
            if tag == "select":
                self.active = False

    parser = Selects()
    parser.feed(html)
    return parser.items


def sync(root: Path, target: str) -> None:
    """Copy completed raw data only; never transmit the native browser profile."""
    if not target:
        return
    subprocess.run(
        [
            "rsync",
            "-az",
            "--partial",
            "--exclude=*.part",
            "--exclude=browser-profile/",
            str(root) + "/",
            target,
        ],
        check=True,
    )


async def run(args: argparse.Namespace) -> None:
    root = args.output.expanduser()
    cache = BrowserCache(root, args.cache_gb)
    async with async_playwright() as pw:
        if not Path(pw.chromium.executable_path).exists():
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"], check=True
            )
        context = await pw.chromium.launch_persistent_context(
            str(root / "browser-profile"),
            headless=False,
            viewport={"width": 1440, "height": 900},
        )
        await context.route("**/*", cache.route)
        context.on("response", cache.on_response)
        page = await context.new_page()
        today = datetime.now(UTC).date()
        season = today.year if today.month >= 7 else today.year - 1
        jobs = []
        try:
            for competition, (region, tournament, country) in LEAGUES.items():
                if args.leagues and competition not in args.leagues:
                    continue
                html = await cache.open(
                    page, f"{BASE}/Regions/{region}/Tournaments/{tournament}", args.wait
                )
                for option in await options(page, cache, html, "seasons"):
                    year = re.search(r"(20\d{2})", option["text"])
                    if not year or not args.since <= int(year[1]) <= season:
                        continue
                    jobs.append(
                        (
                            int(year[1]),
                            competition,
                            country,
                            region,
                            tournament,
                            option["url"],
                        )
                    )
            saved = 0
            for year, competition, country, _region, tournament, season_url in sorted(
                jobs, reverse=True
            ):
                current = year == season
                suffix = f"?mp_snapshot={today.isoformat()}" if current else ""
                html = await cache.open(
                    page, urljoin(BASE, season_url) + suffix, args.wait
                )
                stages = await options(page, cache, html, "stages")
                stages.extend(
                    {"url": m[1], "text": "Default"}
                    for m in re.findall(
                        r"href=(["
                        + "\"'"
                        + r"])([^"
                        + "\"'"
                        + r"]*/Stages/[^"
                        + "\"'"
                        + r"]+)\1",
                        html,
                        re.I,
                    )
                    if "/Fixtures/" in m[1]
                )
                stage_urls = {
                    x["url"]
                    for x in stages
                    if re.search(r"/Stages/\d+", x["url"], re.I)
                }
                for stage_url in sorted(stage_urls):
                    stage_id = int(re.search(r"/Stages/(\d+)", stage_url, re.I)[1])
                    html = await cache.open(
                        page, urljoin(BASE, stage_url) + suffix, args.wait
                    )
                    calendar = embedded(html, "wsCalendar")
                    if not calendar:
                        raise RuntimeError(
                            "No wsCalendar found; report the cached page markup change"
                        )
                    months = sorted(
                        [
                            (int(y), int(m) + 1)
                            for y, ms in calendar["mask"].items()
                            for m in ms
                        ],
                        reverse=True,
                    )
                    for y, m in months:
                        if datetime(y, m, 1, tzinfo=UTC) > datetime.now(UTC):
                            continue
                        url = f"{BASE}/tournaments/{stage_id}/data/?d={y}{m:02d}" + (
                            f"&mp_snapshot={today}" if current else ""
                        )
                        html = await cache.open(page, url, args.wait)
                        from html import unescape

                        content = unescape(re.sub("<[^>]+>", "", html))
                        try:
                            fixture_data = json.loads(content)
                        except ValueError:
                            raise RuntimeError(
                                "Monthly fixtures did not return JSON"
                            ) from None
                        fixtures = [
                            f
                            for t in fixture_data.get("tournaments", [])
                            for f in t.get("matches", [])
                        ]
                        for fixture in sorted(
                            fixtures,
                            key=lambda f: f.get("startTimeUtc", ""),
                            reverse=True,
                        ):
                            mid = fixture["id"]
                            output = root / f"incoming/{mid}.json"
                            if output.exists():
                                continue
                            status = fixture.get(
                                "status", fixture.get("matchStatus", "")
                            )
                            status = str(
                                status.get("displayName", status)
                                if isinstance(status, dict)
                                else status
                            )
                            if status.lower() not in (
                                "6",
                                "ft",
                                "fulltime",
                                "finished",
                                "afterextratime",
                                "afterpenalties",
                                "full time",
                            ):
                                continue
                            html = await cache.open(
                                page, f"{BASE}/Matches/{mid}/Live", args.wait
                            )
                            data = embedded(html, "matchCentreData")
                            if not data or not data.get("events"):
                                raise RuntimeError(f"No matchCentreData in {mid}")
                            capture = {
                                "matchCentreData": data,
                                "context": {
                                    "match_id": mid,
                                    "competition": competition,
                                    "country": country,
                                    "season": f"{year}/{year + 1}",
                                    "competition_id": tournament,
                                    "season_id": int(
                                        re.search(r"/Seasons/(\d+)", season_url, re.I)[
                                            1
                                        ]
                                    ),
                                    "fixture": fixture,
                                },
                            }
                            capture_bytes = len(
                                json.dumps(
                                    capture, ensure_ascii=False, indent=2
                                ).encode()
                            )
                            if cache.bytes + capture_bytes > cache.budget:
                                raise RuntimeError(
                                    "Raw cache budget reached before saving match JSON"
                                )
                            write_json(output, capture)
                            cache.bytes += capture_bytes
                            saved += 1
                            print(
                                json.dumps(
                                    {
                                        "saved": saved,
                                        "match_id": mid,
                                        "competition": competition,
                                        "season": year,
                                    }
                                ),
                                flush=True,
                            )
                            if saved % 20 == 0:
                                sync(root, args.sync_to)
                            if args.limit and saved >= args.limit:
                                return
        finally:
            await cache.drain()
            await context.close()
            sync(root, args.sync_to)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--output", type=Path, default=Path.home() / ".cache/matchpulse/whoscored"
    )
    p.add_argument("--since", type=int, default=2023)
    p.add_argument("--limit", type=int)
    p.add_argument("--leagues", nargs="+", choices=list(LEAGUES))
    p.add_argument(
        "--wait",
        type=float,
        default=2,
        help="Seconds for normal page JS; use 35 for a challenge spike",
    )
    p.add_argument("--cache-gb", type=float, default=10)
    p.add_argument("--sync-to", default=TARGET, help="Empty string disables rsync")
    args = p.parse_args()
    if args.limit is not None and args.limit < 1:
        p.error("--limit must be positive")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("Interrupted; completed files remain resumable.", file=sys.stderr)


if __name__ == "__main__":
    main()
