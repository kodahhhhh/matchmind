-- Apply with python -m matchmind.db.load init. The loader sets
-- matchmind.embed_dim; standalone SQL defaults to 1536.
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS teams (
    team_id bigint PRIMARY KEY, name text NOT NULL
);
CREATE TABLE IF NOT EXISTS matches (
    match_id text PRIMARY KEY,
    source text NOT NULL,
    competition text NOT NULL,
    season text NOT NULL,
    kickoff_ts timestamptz NOT NULL,
    home bigint NOT NULL REFERENCES teams(team_id),
    away bigint NOT NULL REFERENCES teams(team_id),
    score jsonb NOT NULL,
    meta jsonb NOT NULL DEFAULT '{}'
);
-- Missing dates: UTC July 1 of the first year in season, plus zero-based
-- native_id-sorted rank among undated matches in that competition and season
-- in days. Synthetic timestamps are storage keys, never real fixture dates.
-- Dated kickoffs lack source timezone: their wall clock is stored as UTC,
-- not asserted to be a verified UTC kickoff. Preserve originals in meta.
CREATE TABLE IF NOT EXISTS players (
    player_id bigint PRIMARY KEY,
    name text NOT NULL,
    team bigint REFERENCES teams(team_id),
    position text
);
-- players.team/position = last catalogue lineup seen, not historical membership.
-- Historical rosters remain in matches.meta.lineups.
CREATE TABLE IF NOT EXISTS events (
    event_id text NOT NULL,
    match_id text NOT NULL REFERENCES matches(match_id),
    ts timestamptz NOT NULL,
    period smallint NOT NULL CHECK (period BETWEEN 1 AND 5),
    minute integer NOT NULL,
    second integer NOT NULL CHECK (second BETWEEN 0 AND 59),
    team text NOT NULL CHECK (team IN ('home', 'away')),
    player_id bigint REFERENCES players(player_id),
    type text NOT NULL,
    result text,
    type_name text NOT NULL,
    result_name text,
    bodypart_name text,
    x double precision CHECK (x BETWEEN 0 AND 105),
    y double precision CHECK (y BETWEEN 0 AND 68),
    end_x double precision CHECK (end_x BETWEEN 0 AND 105),
    end_y double precision CHECK (end_y BETWEEN 0 AND 68),
    xg double precision,
    vaep double precision,
    vaep_off double precision,
    vaep_def double precision,
    xt double precision,
    sb_xg double precision,
    sequence_id text,
    extra jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (event_id, ts)
);
SELECT create_hypertable('events', 'ts', chunk_time_interval => INTERVAL '90 days',
                         if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS events_match_ts ON events (match_id, ts);
CREATE INDEX IF NOT EXISTS events_match_sequence ON events (match_id, sequence_id);
-- Compression is opt-in after model backfills. No policy during bulk loading.
ALTER TABLE events SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'match_id,team',
    timescaledb.compress_orderby = 'ts,event_id'
);
CREATE MATERIALIZED VIEW IF NOT EXISTS minute_metrics
WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
SELECT time_bucket(INTERVAL '1 minute', ts) AS bucket,
       match_id, team, period,
       count(*) AS event_count,
       count(*) FILTER (WHERE type_name IN ('pass', 'cross', 'throw_in',
           'freekick_short', 'freekick_crossed', 'corner_short', 'corner_crossed',
           'goalkick')) AS passes,
       count(*) FILTER (WHERE type_name IN ('pass', 'cross', 'throw_in',
           'freekick_short', 'freekick_crossed', 'corner_short', 'corner_crossed',
           'goalkick') AND result_name = 'success') AS successful_passes,
       count(*) FILTER (WHERE type_name IN ('shot', 'shot_penalty',
           'shot_freekick')) AS shots,
       sum(xg) AS xg,
       sum(vaep) AS vaep,
       count(*) FILTER (WHERE x > 70) AS final_third_actions,
       count(*) FILTER (WHERE type_name IN ('pass', 'cross', 'carry', 'dribble')
           AND result_name = 'success' AND end_x - x >= 10) AS progressive_actions
FROM events WHERE period < 5
GROUP BY bucket, match_id, team, period WITH NO DATA;
CREATE INDEX IF NOT EXISTS minute_metrics_match_bucket
    ON minute_metrics (match_id, bucket);
-- Raw StatsBomb coordinates already use the acting team's attacking frame.
-- No home/away or half flip in storage. Future SPADL input must use that frame
-- for these aggregate definitions too. Progressive = successful pass/carry
-- gaining >=10 metres along x (provisional definition for W4).
-- Possession is a PASS-SHARE PROXY, not measured possession time.
-- W4 can replace it with its possession-duration calculation.
-- NULL means no passes/final-third actions, or models not yet populated.
-- Include both teams even if only one has events; period separates stoppage
-- time from the next half's overlapping clock minutes.
CREATE OR REPLACE VIEW minute_metrics_view AS
WITH paired AS (
    SELECT match_id, bucket, period, sum(passes) AS total_passes,
           sum(final_third_actions) AS total_final_third_actions
    FROM minute_metrics GROUP BY match_id, bucket, period
)
SELECT p.match_id, p.bucket, p.period,
       floor(extract(epoch FROM (p.bucket - time_bucket(INTERVAL '1 minute',
           m.kickoff_ts))) / 60)::integer AS minute,
       t.team,
       coalesce(a.event_count, 0) AS event_count,
       coalesce(a.passes, 0) AS passes,
       coalesce(a.successful_passes, 0) AS successful_passes,
       coalesce(a.shots, 0) AS shots,
       a.xg, a.vaep,
       coalesce(a.final_third_actions, 0) AS final_third_actions,
       coalesce(a.progressive_actions, 0) AS progressive_actions,
       coalesce(a.passes, 0)::double precision / nullif(p.total_passes, 0)
           AS possession,
       coalesce(a.final_third_actions, 0)::double precision
           / nullif(p.total_final_third_actions, 0) AS field_tilt
FROM paired p JOIN matches m USING (match_id)
CROSS JOIN (VALUES ('home'), ('away')) t(team)
LEFT JOIN minute_metrics a ON a.match_id = p.match_id AND a.bucket = p.bucket
    AND a.period = p.period AND a.team = t.team;
CREATE TABLE IF NOT EXISTS sequences (
    sequence_id text PRIMARY KEY,
    match_id text NOT NULL REFERENCES matches(match_id),
    team text NOT NULL CHECK (team IN ('home', 'away')),
    start_ts timestamptz NOT NULL,
    end_ts timestamptz NOT NULL,
    n_events integer NOT NULL,
    danger double precision,
    events integer[] NOT NULL
);
CREATE INDEX IF NOT EXISTS sequences_match ON sequences (match_id);
DO $$
DECLARE
    dim integer := coalesce(nullif(current_setting('matchmind.embed_dim', true),
                                   '')::integer, 1536);
BEGIN
    IF dim < 1 OR dim > 2000 THEN
        RAISE EXCEPTION 'EMBED_DIM must be between 1 and 2000 for HNSW vector';
    END IF;
    EXECUTE format('CREATE TABLE IF NOT EXISTS commentary (
        sequence_id text PRIMARY KEY REFERENCES sequences(sequence_id),
        match_id text NOT NULL REFERENCES matches(match_id),
        minute integer NOT NULL,
        text text NOT NULL,
        embedding vector(%s),
        search_vector tsvector GENERATED ALWAYS AS
            (to_tsvector(''english'', text)) STORED
    )', dim);
    IF (SELECT atttypmod FROM pg_attribute
        WHERE attrelid = 'commentary'::regclass AND attname = 'embedding') <> dim
    THEN
        RAISE EXCEPTION 'Existing commentary dimension differs from EMBED_DIM';
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS commentary_embedding_hnsw ON commentary
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS commentary_search_gin ON commentary USING gin (search_vector);
CREATE INDEX IF NOT EXISTS commentary_match ON commentary (match_id);
CREATE TABLE IF NOT EXISTS gamestate_windows (
    window_id text PRIMARY KEY,
    match_id text NOT NULL REFERENCES matches(match_id),
    team text NOT NULL CHECK (team IN ('home', 'away')),
    minute integer NOT NULL,
    features jsonb NOT NULL,
    outcome jsonb NOT NULL,
    embedding vector(16)
);
CREATE INDEX IF NOT EXISTS gamestate_windows_embedding_hnsw ON gamestate_windows
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS gamestate_windows_match ON gamestate_windows (match_id);
