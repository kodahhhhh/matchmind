-- W8 metadata is additive; preserve text, vectors and the generated tsvector.
ALTER TABLE commentary ADD COLUMN IF NOT EXISTS facts jsonb;
ALTER TABLE commentary ADD COLUMN IF NOT EXISTS generated_at timestamptz;
ALTER TABLE commentary ADD COLUMN IF NOT EXISTS model text;
ALTER TABLE commentary ADD COLUMN IF NOT EXISTS prompt_version text;
CREATE INDEX IF NOT EXISTS commentary_match_minute ON commentary(match_id, minute);
