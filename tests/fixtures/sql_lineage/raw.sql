-- Raw layer: read from staging
SELECT * FROM staging.events
WHERE created_at >= CURRENT_DATE - 7;
