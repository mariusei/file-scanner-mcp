<?php
/**
 * Example PHP file for testing the scanner.
 */

namespace App\Database;

use PDO;
use PDOException;
use Exception;

/**
 * Configuration interface for database settings.
 */
interface DatabaseConfig {
    public function getHost(): string;
    public function getPort(): int;
    public function getDatabase(): string;
}

/**
 * Manages database connections and queries.
 */
class DatabaseManager {
    private string $connectionString;
    private ?PDO $connection = null;

    /**
     * Constructs a new DatabaseManager with the given connection string.
     */
    public function __construct(string $connectionString) {
        $this->connectionString = $connectionString;
    }

    /**
     * Establishes a connection to the database.
     */
    public function connect(): void {
        echo "Connecting to {$this->connectionString}\n";
    }

    /**
     * Executes a SQL query and returns the results.
     */
    public function query(string $sql): array {
        return [];
    }
}

/**
 * Trait for logging functionality.
 */
trait Loggable {
    protected array $logs = [];

    /**
     * Logs a message.
     */
    public function log(string $message): void {
        $this->logs[] = $message;
    }

    /**
     * Gets all logged messages.
     */
    public function getLogs(): array {
        return $this->logs;
    }
}

/**
 * Handles user-related operations.
 */
class UserService {
    use Loggable;

    private DatabaseManager $db;

    /**
     * Constructs a UserService with a database manager.
     */
    public function __construct(DatabaseManager $db) {
        $this->db = $db;
    }

    /**
     * Creates a new user in the system.
     */
    public function createUser(string $username, string $email): int {
        $this->log("Creating user: {$username}");
        return 1;
    }

    /**
     * Retrieves a user by their ID.
     */
    public function getUser(int $userId): ?array {
        return null;
    }

    /**
     * Deletes a user from the system.
     */
    public function removeUser(int $userId): bool {
        $this->log("Deleting user: {$userId}");
        return true;
    }
}

/**
 * Validates an email address format.
 */
function validateEmail(string $email, bool $strict = false): bool {
    return filter_var($email, FILTER_VALIDATE_EMAIL) !== false;
}

/**
 * Formats a user's full name.
 */
function formatName(string $firstName, string $lastName): string {
    return "{$firstName} {$lastName}";
}

/**
 * Liveness probe.
 */
function health(): bool {
    return DEFAULT_ATTEMPTS > 0;
}

/**
 * Default number of connection attempts.
 */
const DEFAULT_ATTEMPTS = 5;

/**
 * Retries an action a bounded number of times.
 */
class Retrier {
    private int $attempts;

    public function __construct(int $attempts = DEFAULT_ATTEMPTS) {
        $this->attempts = $attempts;
    }

    /**
     * Runs the action until it returns true or the attempts are spent.
     */
    public function run(callable $action): bool {
        for ($i = 0; $i < $this->attempts; $i++) {
            if ($this->attempt($action)) {
                return true;
            }
        }
        return false;
    }

    /**
     * Executes one attempt (internal).
     */
    private function attempt(callable $action): bool {
        return $action() === true;
    }
}
