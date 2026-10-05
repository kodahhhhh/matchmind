-- Additive W4+W7 empirical-analog storage, applied by db.windows.
-- Keep the W5/W6 schema and cosine index. Standardized features use Euclidean
-- distance, so this additional index supports the API's vector_l2 operator.
CREATE TABLE IF NOT EXISTS gamestate_scaling (
    version text PRIMARY KEY,
    scaling jsonb NOT NULL,
    built_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS gamestate_windows_l2_hnsw ON gamestate_windows
    USING hnsw (embedding vector_l2_ops);
