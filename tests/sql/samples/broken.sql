-- Intentionally broken SQL for error handling testing

-- Missing closing parenthesis
CREATE TABLE broken_table (
    id INT PRIMARY KEY,
    name VARCHAR(100)
-- Missing );

-- Invalid syntax
CREATE TABL typo (id INT);

-- Incomplete statement
CREATE VIEW incomplete_view AS

-- Random broken syntax
SELCT * FORM users WEHRE id = @#$%
