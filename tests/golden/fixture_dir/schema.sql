-- Liten, stabil fixture for golden-test av scan_directory-formatet.

CREATE TABLE tasks (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    priority INT DEFAULT 0
);

CREATE INDEX idx_tasks_priority ON tasks (priority);
