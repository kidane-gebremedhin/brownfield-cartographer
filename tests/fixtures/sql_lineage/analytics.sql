WITH base AS (
  SELECT user_id, COUNT(*) AS cnt FROM raw.events GROUP BY 1
)
INSERT INTO analytics.daily_summary
SELECT * FROM base;
