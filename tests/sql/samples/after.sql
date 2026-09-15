-- Example SQL file for testing the scanner

-- Users table to store user information
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Products table
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(10, 2),
    stock_quantity INT DEFAULT 0
);

-- View for active users
CREATE VIEW recent_users AS
SELECT id, username, email
FROM users
WHERE created_at > DATE_SUB(NOW(), INTERVAL 30 DAY);

-- Function to calculate discount
CREATE FUNCTION calculate_discount(price DECIMAL, discount_pct INT, min_price DECIMAL)
RETURNS DECIMAL
RETURN price * (1 - discount_pct / 100.0);

-- Index on username for faster lookups
CREATE INDEX idx_username ON users(username);

-- Stock lookups for the restock job
CREATE INDEX idx_products_stock ON products(stock_quantity);

/* Sale prices as the shop shows them: every product with the
   default discount applied through calculate_discount above. */
CREATE VIEW sale_prices AS
SELECT product_id, name, calculate_discount(price, 10) AS sale_price
FROM products;

-- Seed data lives in its own file
SOURCE seed/products.sql;
