-- W11: additive identity/history tables. No existing match/event tables change.
CREATE TABLE IF NOT EXISTS player_profiles (
    sb_player_id bigint PRIMARY KEY,
    name text NOT NULL,
    short_name text NOT NULL,
    nickname text,
    date_of_birth date,
    height_cm integer CHECK (height_cm > 0),
    foot text,
    position text,
    nationality text,
    tm_player_id bigint,
    wikidata_qid text,
    photo_url text,
    photo_credit text,
    photo_license text,
    caps integer,
    current_club text,
    market_value_eur bigint,
    peak_market_value_eur bigint,
    match_confidence double precision CHECK (match_confidence BETWEEN 0 AND 1),
    CHECK (photo_url IS NULL OR (photo_credit IS NOT NULL AND photo_license IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS player_profiles_tm ON player_profiles (tm_player_id);
-- W11b: positive StatsBomb IDs; TM-only identities are -tm_player_id.
ALTER TABLE player_profiles ADD COLUMN IF NOT EXISTS in_dataset boolean NOT NULL DEFAULT true;
ALTER TABLE player_profiles ADD COLUMN IF NOT EXISTS sources text[] NOT NULL DEFAULT ARRAY['statsbomb']::text[];
ALTER TABLE player_profiles ADD COLUMN IF NOT EXISTS aliases text[] NOT NULL DEFAULT ARRAY[]::text[];
COMMENT ON COLUMN player_profiles.sb_player_id IS 'Positive StatsBomb ID, or -Transfermarkt ID for TM-only profiles';
CREATE INDEX IF NOT EXISTS player_profiles_dataset_value ON player_profiles (in_dataset DESC, market_value_eur DESC);
CREATE TABLE IF NOT EXISTS player_valuations (
    tm_player_id bigint NOT NULL,
    date date NOT NULL,
    value_eur bigint NOT NULL CHECK (value_eur >= 0),
    club text,
    PRIMARY KEY (tm_player_id, date)
);
-- Materialized all-corpus summaries include non-demo matches absent from events.
CREATE TABLE IF NOT EXISTS player_careers (
    sb_player_id bigint PRIMARY KEY REFERENCES player_profiles(sb_player_id),
    summary jsonb NOT NULL
);
