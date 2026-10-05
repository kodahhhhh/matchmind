# WhoScored: capture on your home connection

EC2's headed Chromium received **403, “Attention Required! | Cloudflare”** on
competition, fixture and match-centre pages. Waiting 30 seconds did not resolve
it. No WhoScored match has been downloaded here. A home connection may work;
this has not been verified on the owner's computer.

Use macOS or Linux with `uv`, `rsync`, SSH access to this box over Tailscale and
a working desktop. The script installs ordinary Playwright Chromium if missing.
It opens a real visible browser. It uses no stealth options, proxy service or
CAPTCHA solver. A refusal that remains after the wait stops the run.

One command to retrieve the script and capture a first sample:

```sh
ssh ubuntu@100.97.212.47 'cat ~/hackathon-W13-sources/scripts/sources/whoscored_local_fetch.py' > /tmp/matchpulse-whoscored.py && uv run /tmp/matchpulse-whoscored.py --wait 35 --limit 20
```

If the browser loads normally, continue the resumable bulk capture:

```sh
uv run /tmp/matchpulse-whoscored.py --since 2023
```

It discovers competition → season → fixture stages → monthly fixtures → finished
match centres for the top five leagues and Champions League. Seasons and fixtures
are processed newest first. Use `--leagues 'Champions League'` to prioritize that
competition, or `--since 2020` to extend history. New page loads are sequential
and at least 3.1 seconds apart per host; JSON fetches are at least 1.1 seconds
apart. The default page wait is two seconds after loading. Use `--wait 35` for
sites whose ordinary browser challenge needs longer. No automatic challenge
solution or browser fingerprint modification is attempted.

Raw responses, rendered HTML and complete embedded `matchCentreData` objects
are cached in `./whoscored-cache/`. Completed caches are never requested again.
Current-season discovery URLs include a dated snapshot; finished match-centre
URLs are immutable. The native browser profile stays on your computer and is
excluded from transfers. Cookies are not copied to the server.

Every 20 captures, and on completion or failure, `rsync` transfers completed raw
files to:

```text
ubuntu@100.97.212.47:~/hackathon/data/raw/whoscored/
```

Transfers are resumable; incomplete `.part` files and the browser profile are
excluded. Override the destination with `--sync-to`, or use `--sync-to ''` to
capture without transferring. Default local cache budget is 10 GiB. Do not raise
it without coordinating the server's total raw-cache budget of 40 GiB.

The server importer scans `data/raw/whoscored/incoming/*.json` and legacy
`match_*.json` files. Run from the W13 worktree:

```sh
cd ~/hackathon-W13-sources/backend
nice -n 10 env DATABASE_URL=postgresql://matchmind:matchmind@localhost:5432/matchpulse_staging OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --group models python -m matchpulse.sources.import_full whoscored --load
```

Run it again as new transfers arrive, or add `--watch 60` to keep scanning in
the foreground once per minute. Completed match IDs are skipped; offline exports
are loaded if `--load` is added later. It does
not request WhoScored from EC2. It requires both halves and an observed final
period-end event, validates converted goal counts against the score, retains
Opta qualifiers, exports standard 105×68 SPADL and scores our xG/VAEP/xT. Raw
native IDs are retained alongside namespaced `ws:` match and event IDs. Inferred
socceraction carries are marked explicitly. Incomplete captures are quarantined
in the import report rather than published.

After importing, reconcile full/lite aliases and update identity evidence:

```sh
DATABASE_URL=postgresql://matchmind:matchmind@localhost:5432/matchpulse_staging uv run python -m matchpulse.sources.reconcile --load
uv run --group models python -m matchpulse.sources.identities
```

The discovery markup and monthly JSON path follow soccerdata's public WhoScored
reader. Parser, cache and pacing tests pass offline; live discovery on a usable
connection remains unverified. If markup has changed, keep the cached page and
report the error; do not delete cached refusals to keep retrying. Source terms
are recorded in `SOURCES.md`; the owner accepts responsibility for them.
