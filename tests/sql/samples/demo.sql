-- Demo SQL file showcasing all supported structures

-- User authentication table
CREATE TABLE auth_users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

/* Orders table with foreign key
   Tracks all customer orders */
CREATE TABLE orders (
    order_id INT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    total_amount DECIMAL(12,2),
    status VARCHAR(20),
    FOREIGN KEY (user_id) REFERENCES auth_users(id)
);

-- View for recent orders
CREATE VIEW recent_orders AS
SELECT
    o.order_id,
    u.username,
    o.total_amount,
    o.created_at
FROM orders o
JOIN auth_users u ON o.user_id = u.id
WHERE o.created_at > DATE_SUB(NOW(), INTERVAL 7 DAY);

-- Calculate order total with tax
CREATE FUNCTION calculate_total_with_tax(subtotal DECIMAL, tax_rate DECIMAL)
RETURNS DECIMAL
RETURN subtotal * (1 + tax_rate);

-- Index for faster user lookups
CREATE INDEX idx_username ON auth_users(username);

-- Composite index for order queries
CREATE INDEX idx_order_status_date ON orders(status, created_at DESC);
