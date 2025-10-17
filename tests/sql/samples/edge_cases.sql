-- Edge cases for SQL scanner testing

/* Multi-line comment
   describing the orders table
   with multiple lines */
CREATE TABLE orders (
    order_id INT PRIMARY KEY,
    user_id INT NOT NULL,
    total DECIMAL(12,2),
    status VARCHAR(20),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Table with various data types
CREATE TABLE data_types_test (
    col_int INT,
    col_bigint BIGINT,
    col_smallint SMALLINT,
    col_decimal DECIMAL(10,2),
    col_float FLOAT,
    col_double DOUBLE,
    col_char CHAR(10),
    col_varchar VARCHAR(255),
    col_text TEXT,
    col_blob BLOB,
    col_date DATE,
    col_timestamp TIMESTAMP,
    col_boolean BOOLEAN,
    col_json JSON
);

-- View with complex query
CREATE VIEW order_summary AS
SELECT
    o.order_id,
    u.username,
    o.total,
    o.status
FROM orders o
JOIN users u ON o.user_id = u.id
WHERE o.status = 'completed';

-- Function with multiple parameters
CREATE FUNCTION get_user_total(user_id INT, start_date DATE, end_date DATE)
RETURNS DECIMAL
RETURN 0;

-- Function returning table
CREATE FUNCTION get_recent_orders(days INT)
RETURNS TABLE
RETURN SELECT * FROM orders;

-- Unique index
CREATE UNIQUE INDEX idx_order_ref ON orders(order_id, user_id);

-- Index with specific columns
CREATE INDEX idx_status_date ON orders(status, created_at DESC);

-- Comments without following SQL
-- This is a standalone comment

/* Another standalone
   multi-line comment */
