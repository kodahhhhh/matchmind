# W11b players coverage verification

Measured 2026-10-04T03:38:29.458744+00:00 in `/home/ubuntu/.worktrees/matchmind-players2` on `ws/W11b-players`.

All 7,563 observed StatsBomb identities in the 2,924 training matches retain profiles and precomputed careers. All 50,149 local CC0 TM records are represented: 5,561 dataset bridges and 44,588 TM-only profiles. The complete search catalogue has 52,151 identities. The seven-column map remains unique, and `_READY` is empty.

## Before and after

| Coverage | Before | After | Dataset player share after | Dataset minute share before → after |
|---|---:|---:|---:|---:|
| StatsBomb → TM | 5,241 | 5,561 | 73.5% | 87.8% → 91.2% |
| StatsBomb with Wikidata QID | 299 | 6,937 | 91.7% | 19.1% → 96.5% |
| StatsBomb with licensed, credited photo | 288 | 5,582 | 73.8% | 18.8% → 88.4% |
| StatsBomb with DOB | 5,236 | 6,946 | 91.8% | 87.7% → 96.6% |
| StatsBomb with height | 5,173 | 6,724 | 88.9% | 87.0% → 95.7% |
| StatsBomb with nationality | 7,560 | 7,560 | 100.0% | 100.0% → 100.0% |
| Either TM or Wikidata identity | 5,241 | 6,946 | 91.8% | 87.8% → 96.6% |
| All searchable profiles | 7,563 | 52,151 | — | — |

Across the complete catalogue: 43,790 QIDs, 19,610 licensed photos, 51,509 DOBs, 47,351 heights, 52,095 nationalities, and 656,301 valuation records. DB counts agree: {'profiles': 52151, 'valuations': 656301, 'careers': 7563, 'photos': 19610}. Player coverage counts distinct source identities; minute coverage weights actual observed exposure, including stoppage/extra time. Unused bench-only roster IDs are outside this observed-player denominator.

## Verification

`DATA_DIR=/home/ubuntu/hackathon/data uv run --group models pytest`: **130 passed**, four existing multimethod deprecation warnings, 68.13 seconds. This includes 38 player tests and transactional idempotent reloads in a disposable database, including removal of a stale negative profile. `uv run ruff check .` and `uv run ruff format --check .`: **PASS**, 101 files formatted.

`python -m matchmind.players.verify --origin http://127.0.0.1:8040` validated real HTTP responses against the strict profile/search/leaderboard models, positive and negative namespaces, dataset-first search ordering, ≥0.8 external-match confidence, photo attribution, artifact/map consistency, all-corpus IDs, the reviewed sample, and DB counts. Golden examples were refreshed, including `tests/golden/player_tm_only_example.json` (Erling Haaland, -418560). Core fixture contracts also passed in the full suite. No frontend was changed.

## Local endpoint latency

The router loads artifacts and the substring index during startup. Request timings below begin after startup. Single local client, no production load test; full tests were running concurrently.

| Endpoint | First request ms | Three subsequent requests ms |
|---|---:|---|
| Dataset profile with match context | 64.16 | 16.52, 17.35, 17.66 |
| TM-only profile with match parameter | 2.16 | 1.94, 2.01, 1.94 |
| Bundesliga leaderboard | 145.81 | 1.92, 1.96, 1.88 |

Search: **100 HTTP requests** across ten common/rare/accented/short/empty queries; median **2.17 ms**, p95 **3.19 ms**, max **3.57 ms**. All were under 100 ms. Individual samples and source counts are in `data/processed/players/w11b_verification.json`.

## Provider requests and throttling

The official bulk P2446 query returned 220,613 rows, yielding 220,611 unique bridges; ambiguous TM identifiers were excluded. The QLever basic-biography query returned 241,160 rows with DOB precision and height units. English label/alias indexing covers 378,472 football identities. Full `wbgetentities` requests used 50 IDs, claims/labels/aliases/sitelinks, `maxlag=5`, and multilingual labels. TM-only basic bios use the bulk mirror instead of thousands of redundant entity requests. Commons fetched credited 400-pixel derivatives in batches of 50 titles, with individual file caches and free-licence gating.

| Source job | Logged HTTP attempts | HTTP 200 | HTTP 429 |
|---|---:|---:|---:|
| club-labels | 1 | 1 | 0 |
| commons | 437 | 396 | 41 |
| entities | 286 | 259 | 27 |
| football-aliases | 1 | 1 | 0 |
| football-labels | 1 | 1 | 0 |
| football-names | 5 | 0 | 5 |
| reference-labels | 13 | 8 | 5 |
| tm-bios | 1 | 1 | 0 |
| tm-index | 1 | 1 | 0 |

**746 logged provider attempts; 78 HTTP 429 responses.** Four preliminary diagnostics were not in that log: three small endpoint probes and one non-JSON response from the original broad-name query. Thus this run made 750 provider attempts including diagnostics; no new CC0 downloads were needed. API batches averaged about ten successful calls per minute; Retry-After cooldowns were honored, with no retry beyond five attempts. Expensive compound name/reference queries returned 429 and were replaced with flat queries/small VALUES batches. No maxlag errors were observed. No scraping or TM image requests occurred. Raw requests are cached under `data/raw/players/`, and all network jobs are stopped.

## Coverage by competition and season

TM before → after is shown separately from the new combined TM/Wikidata identity coverage, so retired players without a local TM record remain visible. All columns use distinct observed SB players or actual observed minutes. The JSON coverage artifact also contains QID/photo/DOB/height player and minute counts for every competition-season.

| Competition | Season | Players | TM players before → after | TM minutes before → after | TM/Wikidata players after | TM/Wikidata minutes after | Photos after |
|---|---|---:|---:|---:|---:|---:|---:|
| 1. Bundesliga | 2015/2016 | 477 | 461 → 473 | 97.9% → 99.5% | 473 (99.2%) | 99.5% | 432 |
| 1. Bundesliga | 2023/2024 | 373 | 364 → 371 | 98.3% → 99.6% | 371 (99.5%) | 99.6% | 292 |
| African Cup of Nations | 2023 | 512 | 335 → 357 | 71.0% → 75.6% | 424 (82.8%) | 85.8% | 326 |
| Champions League | 1970/1971 | 24 | 0 → 0 | 0.0% → 0.0% | 20 (83.3%) | 81.8% | 20 |
| Champions League | 1971/1972 | 24 | 0 → 0 | 0.0% → 0.0% | 23 (95.8%) | 95.5% | 23 |
| Champions League | 1972/1973 | 24 | 0 → 0 | 0.0% → 0.0% | 23 (95.8%) | 95.5% | 23 |
| Champions League | 1999/2000 | 28 | 4 → 4 | 15.1% → 15.1% | 28 (100.0%) | 100.0% | 21 |
| Champions League | 2003/2004 | 28 | 12 → 12 | 42.5% → 42.5% | 26 (92.9%) | 93.8% | 18 |
| Champions League | 2004/2005 | 28 | 9 → 9 | 33.2% → 33.2% | 27 (96.4%) | 97.1% | 25 |
| Champions League | 2006/2007 | 28 | 15 → 15 | 55.1% → 55.1% | 28 (100.0%) | 100.0% | 28 |
| Champions League | 2008/2009 | 27 | 22 → 22 | 82.0% → 82.0% | 25 (92.6%) | 94.6% | 25 |
| Champions League | 2009/2010 | 27 | 19 → 25 | 73.6% → 95.3% | 27 (100.0%) | 100.0% | 27 |
| Champions League | 2010/2011 | 27 | 24 → 25 | 86.4% → 90.9% | 26 (96.3%) | 95.5% | 26 |
| Champions League | 2011/2012 | 26 | 23 → 25 | 92.0% → 95.5% | 25 (96.2%) | 95.5% | 25 |
| Champions League | 2012/2013 | 26 | 26 → 26 | 100.0% → 100.0% | 26 (100.0%) | 100.0% | 26 |
| Champions League | 2013/2014 | 28 | 25 → 28 | 86.5% → 100.0% | 28 (100.0%) | 100.0% | 28 |
| Champions League | 2014/2015 | 28 | 28 → 28 | 100.0% → 100.0% | 28 (100.0%) | 100.0% | 28 |
| Champions League | 2015/2016 | 28 | 25 → 28 | 89.0% → 100.0% | 28 (100.0%) | 100.0% | 27 |
| Champions League | 2016/2017 | 28 | 27 → 28 | 95.4% → 100.0% | 28 (100.0%) | 100.0% | 27 |
| Champions League | 2017/2018 | 27 | 25 → 27 | 95.5% → 100.0% | 27 (100.0%) | 100.0% | 27 |
| Champions League | 2018/2019 | 28 | 28 → 28 | 100.0% → 100.0% | 28 (100.0%) | 100.0% | 28 |
| Copa America | 2024 | 339 | 313 → 319 | 94.7% → 96.5% | 336 (99.1%) | 99.7% | 283 |
| Copa del Rey | 1977/1978 | 25 | 0 → 0 | 0.0% → 0.0% | 21 (84.0%) | 87.5% | 13 |
| Copa del Rey | 1982/1983 | 24 | 0 → 0 | 0.0% → 0.0% | 22 (91.7%) | 90.9% | 9 |
| Copa del Rey | 1983/1984 | 25 | 0 → 0 | 0.0% → 0.0% | 19 (76.0%) | 77.4% | 8 |
| FIFA U20 World Cup | 1979 | 26 | 0 → 0 | 0.0% → 0.0% | 13 (50.0%) | 52.4% | 8 |
| FIFA World Cup | 1958 | 34 | 0 → 0 | 0.0% → 0.0% | 29 (85.3%) | 84.1% | 28 |
| FIFA World Cup | 1962 | 22 | 0 → 0 | 0.0% → 0.0% | 20 (90.9%) | 90.9% | 13 |
| FIFA World Cup | 1970 | 93 | 0 → 0 | 0.0% → 0.0% | 75 (80.6%) | 80.1% | 72 |
| FIFA World Cup | 1974 | 84 | 0 → 0 | 0.0% → 0.0% | 72 (85.7%) | 90.9% | 69 |
| FIFA World Cup | 1986 | 52 | 0 → 0 | 0.0% → 0.0% | 46 (88.5%) | 92.1% | 43 |
| FIFA World Cup | 1990 | 25 | 0 → 0 | 0.0% → 0.0% | 25 (100.0%) | 100.0% | 19 |
| FIFA World Cup | 2018 | 604 | 495 → 512 | 86.8% → 89.4% | 549 (90.9%) | 93.0% | 538 |
| FIFA World Cup | 2022 | 680 | 584 → 599 | 89.4% → 91.7% | 615 (90.4%) | 92.5% | 590 |
| Indian Super league | 2021/2022 | 288 | 58 → 61 | 28.2% → 29.6% | 168 (58.3%) | 67.2% | 61 |
| La Liga | 1973/1974 | 24 | 0 → 0 | 0.0% → 0.0% | 21 (87.5%) | 86.4% | 13 |
| La Liga | 2004/2005 | 113 | 37 → 42 | 36.2% → 42.0% | 101 (89.4%) | 94.5% | 60 |
| La Liga | 2005/2006 | 240 | 80 → 95 | 40.1% → 46.7% | 219 (91.2%) | 95.6% | 154 |
| La Liga | 2006/2007 | 314 | 133 → 152 | 47.8% → 54.1% | 295 (93.9%) | 96.6% | 221 |
| La Liga | 2007/2008 | 341 | 170 → 189 | 56.5% → 62.6% | 317 (93.0%) | 96.4% | 249 |
| La Liga | 2008/2009 | 338 | 180 → 197 | 68.9% → 75.7% | 311 (92.0%) | 96.0% | 247 |
| La Liga | 2009/2010 | 362 | 236 → 255 | 78.2% → 83.7% | 345 (95.3%) | 97.5% | 274 |
| La Liga | 2010/2011 | 355 | 271 → 288 | 87.9% → 90.4% | 340 (95.8%) | 97.7% | 290 |
| La Liga | 2011/2012 | 383 | 325 → 344 | 92.4% → 95.5% | 374 (97.7%) | 98.9% | 332 |
| La Liga | 2012/2013 | 354 | 318 → 341 | 93.6% → 98.3% | 342 (96.6%) | 98.4% | 310 |
| La Liga | 2013/2014 | 350 | 316 → 345 | 93.1% → 98.9% | 345 (98.6%) | 98.9% | 306 |
| La Liga | 2014/2015 | 373 | 343 → 366 | 95.9% → 99.1% | 366 (98.1%) | 99.1% | 310 |
| La Liga | 2015/2016 | 539 | 495 → 525 | 93.2% → 98.3% | 525 (97.4%) | 98.3% | 462 |
| La Liga | 2016/2017 | 360 | 333 → 351 | 96.5% → 98.8% | 351 (97.5%) | 98.8% | 305 |
| La Liga | 2017/2018 | 365 | 336 → 359 | 96.3% → 99.1% | 359 (98.4%) | 99.1% | 312 |
| La Liga | 2018/2019 | 362 | 338 → 359 | 96.9% → 99.6% | 359 (99.2%) | 99.6% | 316 |
| La Liga | 2019/2020 | 369 | 341 → 361 | 96.2% → 98.8% | 361 (97.8%) | 98.8% | 303 |
| La Liga | 2020/2021 | 383 | 352 → 374 | 95.8% → 99.1% | 374 (97.7%) | 99.1% | 303 |
| Liga Profesional | 1981 | 25 | 0 → 0 | 0.0% → 0.0% | 23 (92.0%) | 91.9% | 17 |
| Liga Profesional | 1997/1998 | 28 | 0 → 0 | 0.0% → 0.0% | 25 (89.3%) | 87.6% | 16 |
| Ligue 1 | 2015/2016 | 574 | 534 → 560 | 94.8% → 97.8% | 560 (97.6%) | 97.8% | 488 |
| Ligue 1 | 2021/2022 | 328 | 303 → 322 | 96.1% → 99.1% | 322 (98.2%) | 99.1% | 287 |
| Ligue 1 | 2022/2023 | 387 | 357 → 383 | 96.3% → 99.5% | 383 (99.0%) | 99.5% | 350 |
| Major League Soccer | 2023 | 118 | 90 → 98 | 79.1% → 92.5% | 112 (94.9%) | 97.6% | 96 |
| North American League | 1977 | 25 | 0 → 0 | 0.0% → 0.0% | 20 (80.0%) | 81.8% | 7 |
| Premier League | 2003/2004 | 371 | 95 → 96 | 23.2% → 23.3% | 315 (84.9%) | 92.0% | 267 |
| Premier League | 2015/2016 | 550 | 537 → 549 | 98.4% → 99.8% | 549 (99.8%) | 99.8% | 529 |
| Serie A | 1986/1987 | 26 | 0 → 0 | 0.0% → 0.0% | 25 (96.2%) | 95.5% | 12 |
| Serie A | 2015/2016 | 551 | 512 → 542 | 93.0% → 98.9% | 542 (98.4%) | 98.9% | 454 |
| UEFA Euro | 2020 | 490 | 427 → 448 | 91.6% → 94.6% | 457 (93.3%) | 95.3% | 438 |
| UEFA Euro | 2024 | 493 | 449 → 482 | 91.3% → 98.2% | 483 (98.0%) | 98.3% | 435 |
| UEFA Europa League | 1988/1989 | 54 | 0 → 0 | 0.0% → 0.0% | 53 (98.1%) | 95.5% | 19 |

## New-mapping spot check

Thirty new mappings were selected with pandas random_state=2026 from the first 1,659 new proposals and revalidated against the final published map. All were previously TM-unmatched. **30 accepted; 0 rejected in this reviewed sample.** Name/alias equivalence, citizenship, age plausibility and available qualified club spells were inspected directly from cached source evidence. Some P54 memberships have no dates; those are explicitly identified below and were not treated as dated evidence. This is a heuristic mapping review, not a population precision estimate or an independent DOB verification. Raw evidence and individual verdicts: `data/processed/players/spot_check_w11b.json`.

| SB ID | TM ID / QID | StatsBomb name | Verdict | Evidence reviewed |
|---:|---|---|---|---|
| 5508 | Q2602888 | Birkir Már Sævarsson | Accept | Accent/transliteration aliases; Iceland; 1984 birth fits 2018 national-team appearances; P54 Iceland spell spans 2007-2021. |
| 44307 | Q66493804 | Cédric Badolo | Accept | Exact accented name; Burkina Faso; 1998 birth fits AFCON 2024. P54 is unqualified; dated club corroboration unavailable. |
| 34392 | Q239914 | Steve Finnan | Accept | Steve/Stephen Finnan aliases; Ireland; 1976 birth; P54 Liverpool 2003-2008 overlaps observed finals. |
| 162755 | Q24007416 | Mohammed Irshad | Accept | Mohammed Irshad and T.V. Mohamed Irshad aliases; India; 1994 birth fits 2021. P54 lacks a dated Northeast United spell. |
| 205682 | 819603 / Q101771882 | Noah Allen | Accept | Noah/Noah James Allen aliases; US citizenship also in Wikidata despite Greek TM citizenship; 2004 birth fits 2023; Inter Miami membership present but unqualified. |
| 164476 | Q345556 | Łukasz Gikiewicz | Accept | Polish L transliteration; Poland; 1987 birth fits 2021. Wikidata lacks a dated Chennaiyin spell. |
| 26525 | Q2713245 | Asier Goiria Etxebarria | Accept | Full paternal name shortened to Asier Goiria; Spain; 1980 birth; Numancia membership 2008-2010 agrees. |
| 398607 | Q5371842 | Emilio Nicolás Commisso | Accept | Middle name omitted from Emilio Commisso; Argentina; 1956 birth; River Plate 1976-1983 overlaps 1981 match. |
| 15778 | Q227892 | Alessandro Nesta | Accept | Exact name; Italy; 1976 birth; Milan 2002-2012 overlaps 2005/2007 finals. |
| 187212 | 67955 / Q3557205 | Marcelo Leite Pereira | Accept | Exact full name plus Marcelinho nickname; Brazil; 1987 birth. Dated 2022 Northeast United spell unavailable. |
| 6619 | 44699 / Q442821 | Vitorino Gabriel Pacheco Antunes | Accept | Antunes full-name/nickname equivalence; Portugal; 1987 birth; Malaga 2013-2015 and Getafe 2017-2020 overlap. |
| 39947 | Q922940 | Giuseppe Bruscolotti | Accept | Exact name; Italy; 1951 birth; Napoli 1972-1988 overlaps 1986 match. |
| 164495 | Q28823363 | Edwin Sydney Vanspaul | Accept | Exact three-part name; India; 1992 birth fits 2021; P54 has no dated Chennaiyin spell. |
| 398855 | Q677720 | Héctor Eduardo Chumpitáz González | Accept | Accent and expanded name equivalence; Peru; 1944 birth; Peru 1965-1981 overlaps 1970 World Cup. |
| 38657 | Q346942 | Óscar Alfredo Ruggeri Zocola | Accept | Middle/maternal names shortened to Oscar Ruggeri; Argentina; 1962 birth; Boca 1980-1984 and Argentina 1983-1994 agree. |
| 25040 | 624690 / Q64029237 | Kouadio Emmanuel Koné | Accept | Manu Kone/full Kouadio Emmanuel Boris Kone aliases; France; 2001 birth; cached TM appearance supplies dated Monchengladbach evidence. |
| 38403 | Q318103 | Shaka Hislop | Accept | Neil/Shaka Hislop aliases; Trinidad and Tobago; 1969 birth; Portsmouth 2002-2005 agrees. |
| 39641 | Q170376 | Gabriel Omar Batistuta | Accept | Gabriel Omar Batistuta/full and short aliases; Argentina citizenship among dual citizenships; 1969 birth; Fiorentina 1991-2000 agrees. |
| 398835 | Q98084 | Rainer Zietsch | Accept | Exact name; Germany; 1964 birth; Stuttgart 1983-1989 overlaps 1989 match. |
| 39713 | Q17163 | Johan Cruyff | Accept | Cruyff/Cruijff spelling aliases; Netherlands; 1947 birth; Ajax 1964-1973 overlaps all observed early finals. |
| 102667 | Q56610831 | Hemeya Tanjy | Accept | Exact name; Mauritania; 1998 birth fits AFCON 2024; P54 unqualified, dated club corroboration unavailable. |
| 40445 | Q437322 | Danny Higginbotham | Accept | Exact name; Gibraltar/UK citizenship explains international affiliation; 1978 birth; Southampton 2003-2006 agrees. |
| 19757 | Q659634 | Anderson Luís de Souza | Accept | Deco/full Anderson Luis de Souza aliases; Portugal and Brazil; 1977 birth; Porto 1999-2004 and Barcelona 2004-2008 agree. |
| 10573 | 137313 / Q2715932 | Jonathan Buatu Mananga | Accept | Exact expanded name; Angola/Belgium citizenship; 1993 birth; Angola spell starts 2014, overlapping AFCON 2024. |
| 3067 | 238223 / Q17074511 | Ederson Santana de Moraes | Accept | Ederson/full Ederson Santana de Moraes aliases; Brazil; 1993 birth fits 2018 national-team context; bulk biography has no P54 qualifiers. |
| 40223 | Q516985 | Antoine Sibierski | Accept | Exact name; France; 1974 birth; Manchester City 2003-2006 agrees. |
| 39921 | Q44389 | Bernd Schuster | Accept | Exact name and Bernardo/Schuster aliases; Germany/West Germany; 1959 birth; Barcelona 1980-1988 agrees. |
| 12580 | Q7926408 | Victor Ulloa | Accept | Exact name; Mexico/US citizenship; 1992 birth; Inter Miami spell starts 2020, overlaps 2023. |
| 38617 | Q44820 | Georg Schwarzenbeck | Accept | Georg/Hans-Georg Schwarzenbeck aliases; Germany; 1948 birth; Germany 1971-1978 overlaps 1974. |
| 110050 | 735811 / Q86422506 | Jonathan Bell | Accept | Jonathan/Jon Bell aliases; US/Jamaica citizenship explains StatsBomb country vs national-team context; 1997 birth fits Copa 2024; no dated P54 in bulk bio. |

## Integration and limits

The explicitly requested W11b extension adds `in_dataset` and `sources` to profiles, `in_dataset` to search results, nullable career/heatmap for TM-only records, and negative TM-only IDs. Every existing field remains. Leaderboard formulas/shape and dataset-only scope are unchanged. All 2,924 match summaries, event/sequence citations and model outputs are retained.

The orchestrator owns shared fixtures, frontend integration, merge and release. Update `fixtures/players/{5503,search}.json` from the refreshed golden examples; add the TM-only example if needed, and guard nullable career/heatmap in the frontend. After merging, restart the consumer to replace its process caches. The shared :8000 process was never restarted; isolated :8040 was stopped after verification. Nothing was pushed or merged.

Unmatched names, collisions and missing source metadata stay null. Matching confidence is heuristic. Of 634 local TM/Wikidata full-date discrepancies, 113 birth-year conflicts (two dataset players) invalidate the QID/photo bridge; same-year disagreements retain TM DOB. The three dataset players without nationality remain null. Photos with missing author, unrecognized/nonfree licence or missing file info are excluded. QLever is a source snapshot; detailed official entity claims take precedence where fetched. Career coverage is this uneven selected training corpus, not a complete professional career. Full suite, source caches and local API evidence do not constitute a production concurrency test.
