# Wyscout public files and offline importer

Round 2 successfully downloaded these files with genuine headed Playwright
Chromium. The figshare article still returned HTTP 202, but the public download
host completed normal downloads. **No manual owner download is currently needed.**

If rebuilding on another box, the dataset is Pappalardo et al. 2019, CC BY 4.0:
[figshare dataset](https://figshare.com/collections/Soccer_match_event_dataset/4415000).
Keep attribution and the source receipts with the raw files.

| Filename | Public file URL | Downloaded bytes |
|---|---|---:|
| events.zip | https://ndownloader.figshare.com/files/14464685 | 77,323,413 |
| matches.zip | https://ndownloader.figshare.com/files/14464622 | 645,097 |
| competitions.json | https://ndownloader.figshare.com/files/15073685 | 1,209 |
| teams.json | https://ndownloader.figshare.com/files/15073697 | 27,404 |
| players.json | https://ndownloader.figshare.com/files/15073721 | 1,737,347 |

Place completed downloads under `data/raw/wyscout/incoming/`. The importer
extracts only these expected JSON filenames into `data/raw/wyscout/dataset/`:

```text
events_England.json                 matches_England.json
events_France.json                  matches_France.json
events_Germany.json                 matches_Germany.json
events_Italy.json                   matches_Italy.json
events_Spain.json                   matches_Spain.json
events_European_Championship.json    matches_European_Championship.json
events_World_Cup.json               matches_World_Cup.json
teams.json                         players.json
competitions.json
```

Extracted expected JSON files may also be supplied directly in `incoming/`.
Archive symlinks, unexpected paths and over-budget archive expansion are rejected
or ignored. Extraction is offline and idempotent; no implicit socceraction
loader download is used.

```sh
cd ~/hackathon-W13-sources/backend
nice -n 10 env DATABASE_URL=postgresql://matchmind:matchmind@localhost:5432/matchpulse_staging OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --group models python -m matchpulse.sources.import_full wyscout --load
```

This scans newly supplied files, skips completed exports, prefers existing
StatsBomb matches by dated team identity, and loads only `matchpulse_staging`.
Per-source catalogue and standard SPADL parquet exports live in
`data/sources/catalogue_wyscout.json` and `data/sources/wyscout/spadl/`.
