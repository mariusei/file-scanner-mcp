-- PostgreSQL-specific SQL features test file
-- Tests DO blocks, PL/pgSQL, partitioning, and PostgreSQL-specific syntax

-- Simple DO block with RAISE NOTICE
DO $$
BEGIN
    RAISE NOTICE 'Starting migration';
END $$;

-- DO block with declarations and variables
DO $$
DECLARE
    row_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO row_count FROM pg_tables;
    RAISE NOTICE 'Found % tables', row_count;
END $$;

-- CREATE TABLE with PostgreSQL-specific features
CREATE UNLOGGED TABLE test_data (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- PostgreSQL partitioned table
CREATE TABLE measurements (
    city_id INTEGER NOT NULL,
    log_date DATE NOT NULL,
    temp_hi INTEGER,
    temp_lo INTEGER
) PARTITION BY RANGE (log_date);

-- CREATE INDEX with INCLUDE (covering index)
CREATE INDEX idx_test_data_name
ON test_data (name) INCLUDE (data);

-- CREATE FUNCTION with RETURNS TABLE
CREATE FUNCTION get_recent_data(days INTEGER)
RETURNS TABLE(id INTEGER, name TEXT)
AS $$
BEGIN
    RETURN QUERY
    SELECT t.id, t.name
    FROM test_data t
    WHERE t.created_at > CURRENT_DATE - days;
END;
$$ LANGUAGE plpgsql;

-- DO block with dynamic SQL using EXECUTE FORMAT
DO $$
DECLARE
    table_name TEXT := 'test_data';
BEGIN
    EXECUTE FORMAT('ANALYZE %I', table_name);
    RAISE NOTICE 'Analyzed table %', table_name;
END $$;

-- CREATE VIEW
CREATE VIEW recent_data AS
SELECT id, name, created_at
FROM test_data
WHERE created_at > CURRENT_DATE - INTERVAL '7 days';

-- ALTER TABLE with constraint
ALTER TABLE test_data
ADD CONSTRAINT test_data_name_check CHECK (length(name) > 0);

-- PostgreSQL-specific INSERT with ON CONFLICT
INSERT INTO test_data (id, name, data)
VALUES (1, 'test', '{"key": "value"}')
ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data;
