CREATE TABLE demo_records (
    id BIGSERIAL PRIMARY KEY,
    external_id TEXT NOT NULL
);

INSERT INTO demo_records (external_id)
SELECT md5(value::text)
FROM generate_series(1, 1000000) AS value;

CREATE UNIQUE INDEX demo_records_external_id_idx
ON demo_records (external_id);

ANALYZE demo_records;
