W4+W7 adds `gamestate_api.sql` and `windows.py`; no event/model columns change.

From `backend/`, with the shared `DATA_DIR` configured:

```sh
uv run python -m matchmind.db.windows
```

This builds both-team game states every five elapsed minutes for all 493 demo
matches. Windows require a complete next-15-minute horizon. The states use
minute, score difference, possession pass share, field tilt, xG/VAEP/xT rates for
and against, shots for and against, time since each team's last substitution,
and each team's players remaining. Stored embeddings are standardized numeric
features, not language embeddings. Mean/scale and feature order live in
`gamestate_scaling`, version `analog:v1`.

The loader atomically replaces only `analog:v1:` windows; other versions are
preserved. The additive HNSW L2 index supports Euclidean distance over those
features, alongside W5's cosine index. Requests exclude the anchor match and
use 40 neighbours. The first five real windows are returned as analogs. Outcome
bands and cumulative series are empirical quantiles of observed neighbour
outcomes; `models.gamestate.quantile_bands` is the replacement seam for W6.

After W3 backfills `events.xg`, `vaep`, `vaep_off`, `vaep_def`, `xt`, rebuild the
windows with this command and restart the API (or invoke
`api.repository.clear_cache` in-process). GET caches also expire every five
minutes. `extra` must retain raw StatsBomb source events and source index IDs.

The model uses no causal identification, fatigue/injury covariates, or player
identity. Late anchors have a truncated actual horizon at full time, while the
modelled band uses full historical horizons. Never interpret it as a causal
estimate. All model output retains the fixture's label and caveat.
