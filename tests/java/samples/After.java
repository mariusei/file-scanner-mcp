/**
 * Example Java file for testing the scanner.
 */

package com.example.demo;

import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Configuration interface for application settings.
 */
public interface Config {
    String getApiKey();
    String getEndpoint();
    int getTimeout();
}

/**
 * Manages database connections and queries.
 */
public class DatabaseManager {
    private String connectionString;
    private Object connection;

    /**
     * Constructs a new DatabaseManager with the given connection string.
     */
    public DatabaseManager(String connectionString) {
        this.connectionString = connectionString;
        this.connection = null;
    }

    /**
     * Establishes a connection to the database.
     */
    public void connect() {
        System.out.println("Connecting to " + connectionString);
    }

    /**
     * Liveness probe.
     */
    public boolean health() {
        return connection != null;
    }

    /**
     * Executes a SQL query and returns the results.
     */
    public List<Map<String, Object>> query(String sql) {
        return List.of();
    }
}

/**
 * Handles user-related operations.
 */
public class UserService {
    private DatabaseManager db;

    /**
     * Constructs a UserService with a database manager.
     */
    public UserService(DatabaseManager db) {
        this.db = db;
    }

    /**
     * Creates a new user in the system.
     */
    public int createUser(String username, String email) {
        return 1;
    }

    /**
     * Retrieves a user by their ID.
     */
    public Optional<Map<String, Object>> getUser(int userId) {
        return Optional.empty();
    }

    /**
     * Deletes a user from the system.
     */
    public boolean removeUser(int userId) {
        return true;
    }
}

/**
 * Utility class for email validation.
 */
public class EmailValidator {
    /**
     * Validates an email address format.
     */
    public static boolean validateEmail(String email, boolean strict) {
        return email != null && email.contains("@");
    }
}

/**
 * Retries a connection until it succeeds or the budget is spent.
 */
public class ConnectionRetrier {
    /** Retry budget for connection attempts. */
    public static final int MAX_RETRIES = 5;

    /**
     * Connects, retrying up to MAX_RETRIES times.
     */
    public static boolean retryConnect(DatabaseManager db) {
        for (int attempt = 0; attempt < MAX_RETRIES; attempt++) {
            if (tryConnect(db)) {
                return true;
            }
        }
        return false;
    }

    private static boolean tryConnect(DatabaseManager db) {
        db.connect();
        return EmailValidator.validateEmail("ada@example.com");
    }
}
