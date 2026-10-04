# W11 verification

Measured 2026-10-04T02:12:23.741021+00:00 in the W11 worktree.

The map contains 7,563 observed-player identities; 5,241 have a unique TM bridge (69.3% of players; 87.8% of observed minutes). `_READY` exists and is empty.

Profiles: 7,563; historical valuations: 141,999; career: 2,924 matches / 82,500 appearances / 7,563 players. DB counts: (7563, 141999, 7563, 288). Photos: 288 (3.8%); QIDs: 299. A conflicting birth-year QID/photo was removed. Wikidata enrichment is partial because the source returned HTTP 429; later cooled-down batches succeeded. Unfetched metadata remains null.

`uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest`: PASS, 108 tests (16 W11 tests), four existing multimethod deprecation warnings. DATA_DIR points to the shared data directory. The shared :8000 process was never restarted. An isolated :8040 app served actual artifacts and validated all three endpoint models; that process was stopped.

## Coverage by competition and season

| Competition | Season | Players matched / observed | Player share | Minute share |
|---|---|---:|---:|---:|
| 1. Bundesliga | 2015/2016 | 461 / 477 | 96.6% | 97.9% |
| 1. Bundesliga | 2023/2024 | 364 / 373 | 97.6% | 98.3% |
| African Cup of Nations | 2023 | 335 / 512 | 65.4% | 71.0% |
| Champions League | 1970/1971 | 0 / 24 | 0.0% | 0.0% |
| Champions League | 1971/1972 | 0 / 24 | 0.0% | 0.0% |
| Champions League | 1972/1973 | 0 / 24 | 0.0% | 0.0% |
| Champions League | 1999/2000 | 4 / 28 | 14.3% | 15.1% |
| Champions League | 2003/2004 | 12 / 28 | 42.9% | 42.5% |
| Champions League | 2004/2005 | 9 / 28 | 32.1% | 33.2% |
| Champions League | 2006/2007 | 15 / 28 | 53.6% | 55.1% |
| Champions League | 2008/2009 | 22 / 27 | 81.5% | 82.0% |
| Champions League | 2009/2010 | 19 / 27 | 70.4% | 73.6% |
| Champions League | 2010/2011 | 24 / 27 | 88.9% | 86.4% |
| Champions League | 2011/2012 | 23 / 26 | 88.5% | 92.0% |
| Champions League | 2012/2013 | 26 / 26 | 100.0% | 100.0% |
| Champions League | 2013/2014 | 25 / 28 | 89.3% | 86.5% |
| Champions League | 2014/2015 | 28 / 28 | 100.0% | 100.0% |
| Champions League | 2015/2016 | 25 / 28 | 89.3% | 89.0% |
| Champions League | 2016/2017 | 27 / 28 | 96.4% | 95.4% |
| Champions League | 2017/2018 | 25 / 27 | 92.6% | 95.5% |
| Champions League | 2018/2019 | 28 / 28 | 100.0% | 100.0% |
| Copa America | 2024 | 313 / 339 | 92.3% | 94.7% |
| Copa del Rey | 1977/1978 | 0 / 25 | 0.0% | 0.0% |
| Copa del Rey | 1982/1983 | 0 / 24 | 0.0% | 0.0% |
| Copa del Rey | 1983/1984 | 0 / 25 | 0.0% | 0.0% |
| FIFA U20 World Cup | 1979 | 0 / 26 | 0.0% | 0.0% |
| FIFA World Cup | 1958 | 0 / 34 | 0.0% | 0.0% |
| FIFA World Cup | 1962 | 0 / 22 | 0.0% | 0.0% |
| FIFA World Cup | 1970 | 0 / 93 | 0.0% | 0.0% |
| FIFA World Cup | 1974 | 0 / 84 | 0.0% | 0.0% |
| FIFA World Cup | 1986 | 0 / 52 | 0.0% | 0.0% |
| FIFA World Cup | 1990 | 0 / 25 | 0.0% | 0.0% |
| FIFA World Cup | 2018 | 495 / 604 | 82.0% | 86.8% |
| FIFA World Cup | 2022 | 584 / 680 | 85.9% | 89.4% |
| Indian Super league | 2021/2022 | 58 / 288 | 20.1% | 28.2% |
| La Liga | 1973/1974 | 0 / 24 | 0.0% | 0.0% |
| La Liga | 2004/2005 | 37 / 113 | 32.7% | 36.2% |
| La Liga | 2005/2006 | 80 / 240 | 33.3% | 40.1% |
| La Liga | 2006/2007 | 133 / 314 | 42.4% | 47.8% |
| La Liga | 2007/2008 | 170 / 341 | 49.9% | 56.5% |
| La Liga | 2008/2009 | 180 / 338 | 53.3% | 68.9% |
| La Liga | 2009/2010 | 236 / 362 | 65.2% | 78.2% |
| La Liga | 2010/2011 | 271 / 355 | 76.3% | 87.9% |
| La Liga | 2011/2012 | 325 / 383 | 84.9% | 92.4% |
| La Liga | 2012/2013 | 318 / 354 | 89.8% | 93.6% |
| La Liga | 2013/2014 | 316 / 350 | 90.3% | 93.1% |
| La Liga | 2014/2015 | 343 / 373 | 92.0% | 95.9% |
| La Liga | 2015/2016 | 495 / 539 | 91.8% | 93.2% |
| La Liga | 2016/2017 | 333 / 360 | 92.5% | 96.5% |
| La Liga | 2017/2018 | 336 / 365 | 92.1% | 96.3% |
| La Liga | 2018/2019 | 338 / 362 | 93.4% | 96.9% |
| La Liga | 2019/2020 | 341 / 369 | 92.4% | 96.2% |
| La Liga | 2020/2021 | 352 / 383 | 91.9% | 95.8% |
| Liga Profesional | 1981 | 0 / 25 | 0.0% | 0.0% |
| Liga Profesional | 1997/1998 | 0 / 28 | 0.0% | 0.0% |
| Ligue 1 | 2015/2016 | 534 / 574 | 93.0% | 94.8% |
| Ligue 1 | 2021/2022 | 303 / 328 | 92.4% | 96.1% |
| Ligue 1 | 2022/2023 | 357 / 387 | 92.2% | 96.3% |
| Major League Soccer | 2023 | 90 / 118 | 76.3% | 79.1% |
| North American League | 1977 | 0 / 25 | 0.0% | 0.0% |
| Premier League | 2003/2004 | 95 / 371 | 25.6% | 23.2% |
| Premier League | 2015/2016 | 537 / 550 | 97.6% | 98.4% |
| Serie A | 1986/1987 | 0 / 26 | 0.0% | 0.0% |
| Serie A | 2015/2016 | 512 / 551 | 92.9% | 93.0% |
| UEFA Euro | 2020 | 427 / 490 | 87.1% | 91.6% |
| UEFA Euro | 2024 | 449 / 493 | 91.1% | 91.3% |
| UEFA Europa League | 1988/1989 | 0 / 54 | 0.0% | 0.0% |

## Manual random spot check

Sample: 30 mappings selected with pandas random_state=2026 from the final matched map. I inspected name/nickname equivalence, TM date of birth/nationality and the earliest observed team/season. All 30 final-sample mappings were accepted. An earlier sample exposed retired Raul Gonzalez incorrectly mapped to young Raul Blanco; the age check rejects that mapping and leaves it unmatched. This sample is not a population precision estimate. Raw evidence: `data/processed/players/spot_check.json`.

| SB ID | TM ID | StatsBomb name | TM name | Verdict | Review |
|---:|---:|---|---|---|---|
| 31900 | 59322 | Oleksandr Karavaev | Oleksandr Karavaev | Accept | Exact name after accents/punctuation normalization; DOB and observed career era agree. |
| 8517 | 39015 | Ralf Fährmann | Ralf Fährmann | Accept | Exact name after accents/punctuation normalization; DOB and observed career era agree. |
| 6351 | 59323 | Cristhian Ricardo Stuani Curbelo | Cristhian Stuani | Accept | Cristhian Stuani: full paternal name retained; Uruguay, 1986 and Levante era agree. |
| 4041 | 80197 | José Salomón Rondón Giménez | Salomón Rondón | Accept | Salomon Rondon: maternal surname omitted; Venezuela, 1989 and Malaga era agree. |
| 6902 | 448344 | Óscar Melendo Jiménez | Óscar Melendo | Accept | Oscar Melendo: maternal surname omitted; Spain, 1997 and Espanyol era agree. |
| 3481 | 127032 | Serge Aurier | Serge Aurier | Accept | Exact name after accents/punctuation normalization; DOB and observed career era agree. |
| 12603 | 272999 | Miguel Ángel Almirón Rejala | Miguel Almirón | Accept | Miguel Almiron: middle/maternal names omitted; Paraguay, 1994 agree. |
| 10014 | 117432 | Kevin Behrens | Kevin Behrens | Accept | Exact name after accents/punctuation normalization; DOB and observed career era agree. |
| 15960 | 119213 | Richmond Yiadom Boakye | Richmond Boakye | Accept | Richmond Boakye: middle name omitted; 1993 and Elche game context agree; TM citizenship missing. |
| 8949 | 245744 | Takuma Asano | Takuma Asano | Accept | Exact name after accents/punctuation normalization; DOB and observed career era agree. |
| 3420 | 113707 | Rémy Cabella | Rémy Cabella | Accept | Exact name after accents/punctuation normalization; DOB and observed career era agree. |
| 4053 | 13572 | Ben Foster | Ben Foster | Accept | Exact name after accents/punctuation normalization; DOB and observed career era agree. |
| 7123 | 21872 | Gianluca Pegolo | Gianluca Pegolo | Accept | Exact name after accents/punctuation normalization; DOB and observed career era agree. |
| 6299 | 255450 | Aleksey Miranchuk | Aleksey Miranchuk | Accept | Exact name after accents/punctuation normalization; DOB and observed career era agree. |
| 40127 | 61834 | Ryan Mason | Ryan Mason | Accept | Exact name after accents/punctuation normalization; DOB and observed career era agree. |
| 16295 | 44855 | Dame N''Doye | Dame N'Doye | Accept | Dame N Doye: source apostrophe duplication only; Senegal and 1985 agree. |
| 10836 | 224672 | Sergio Fernando Peña Flores | Sergio Peña | Accept | Sergio Pena: middle/maternal names omitted; Peru and 1995 agree. |
| 38552 | 3292 | Joey Barton | Joey Barton | Accept | Exact name after accents/punctuation normalization; DOB and observed career era agree. |
| 48246 | 526845 | Noah Atubolu | Noah Atubolu | Accept | Exact name after accents/punctuation normalization; DOB and observed career era agree. |
| 8202 | 53719 | Ariel Borysiuk | Ariel Borysiuk | Accept | Exact name after accents/punctuation normalization; DOB and observed career era agree. |
| 8402 | 119169 | Aron Jóhannsson | Aron Jóhannsson | Accept | Exact name after accents/punctuation normalization; DOB and observed career era agree. |
| 41202 | 405564 | Giorgi Kochorashvili | Giorgi Kochorashvili | Accept | Exact name after accents/punctuation normalization; DOB and observed career era agree. |
| 5688 | 119235 | Carlos Arturo Bacca Ahumada | Carlos Bacca | Accept | Carlos Bacca: middle/maternal names omitted; Colombia, 1986 and Sevilla era agree. |
| 7355 | 243725 | Olivier Michel Kemen | Olivier Kemen | Accept | Olivier Kemen: middle name omitted; Cameroon, 1996 and Lyon era agree. |
| 33221 | 532775 | Melvin Bard | Melvin Bard | Accept | Exact name after accents/punctuation normalization; DOB and observed career era agree. |
| 9904 | 191614 | Frederico Rodrigues Santos | Fred | Accept | Fred: StatsBomb nickname identifies Frederico Rodrigues Santos; Brazil and 1993 agree. |
| 15519 | 3226 | Nicolas Anelka | Nicolas Anelka | Accept | Exact name after accents/punctuation normalization; DOB and observed career era agree. |
| 3610 | 202984 | Roque Mesa Quevedo | Roque Mesa | Accept | Roque Mesa: maternal surname omitted; Spain, 1989 and Las Palmas era agree. |
| 21131 | 439914 | John Yeboah Zamora | John Yeboah | Accept | John Yeboah: maternal surname omitted; Ecuador and 2000 agree. |
| 6838 | 73636 | Hernán Arsenio Pérez González | Hernán Pérez | Accept | Hernan Perez: middle/maternal names omitted; Paraguay, 1989 and Espanyol era agree. |

## Endpoint latency on :8040

Single local client; first request includes cold process/artifact work. Warm values are three subsequent samples, not a production load test.

| Endpoint | First request ms | Warm requests ms | HTTP |
|---|---:|---|---:|
| `/api/players/5503?match_id=sb:3869685` | 2825.67 | 17.1, 16.52, 16.46 | 200 |
| `/api/players?q=mbappe&limit=5` | 40.96 | 39.91, 40.6, 40.57 | 200 |
| `/api/players/leaderboard?metric=vaep_per90&min_minutes=900&competition=1.%20Bundesliga&season=2015%2F2016&limit=5` | 264.12 | 2.58, 2.59, 2.38 | 200 |
| `/api/players/leaderboard?metric=vaep_per90&min_minutes=900&limit=50` | 1118.65 | 2.16, 1.88, 1.6 | 200 |

## Integration and limits

Register `matchmind.api.routes.players.router` in the shared API with `prefix="/api"`; see OPERATIONS.md for the exact two lines. API main.py and fixtures are outside W11 ownership. Merge/release/restart belongs to the orchestrator. Existing fixture/schema contracts are untouched; new golden examples and Pydantic models cover the requested shapes. Keep the models dependency group installed for parquet runtime reads.

Confidence is heuristic. Ancient competitions and India have low TM coverage. The map deliberately leaves ambiguous names/duplicate bridges unmatched. Some dates and values stay null. Metrics cover this selected training corpus, not a complete career; live/provider analyst generation with the new tool was not separately exercised. Top moments cite real raw indices/possession IDs and include 15,858 available DB commentary texts.

Leaderboard formula and definitions are documented in OPERATIONS.md.
