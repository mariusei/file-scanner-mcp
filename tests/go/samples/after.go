// Package example demonstrates basic Go structures
package example

import (
	"fmt"
	"time"
)

// Config holds application configuration
type Config struct {
	Host string
	Port int
}

// Logger is an interface for logging operations
type Logger interface {
	Log(message string) error
	LogError(err error)
}

// DatabaseManager manages database connections and queries
type DatabaseManager struct {
	connectionString string
	connected        bool
}

// NewDatabaseManager creates a new DatabaseManager instance
func NewDatabaseManager(connStr string) *DatabaseManager {
	return &DatabaseManager{
		connectionString: connStr,
		connected:        false,
	}
}

// Connect establishes database connection
func (db *DatabaseManager) Connect() error {
	fmt.Println("Connecting to database")
	db.connected = true
	return nil
}

// Health is a liveness probe
func Health() bool {
	return true
}

// Query executes a SQL query and returns results
func (db *DatabaseManager) Query(sql string) ([]map[string]interface{}, error) {
	return nil, nil
}

// UserService handles user-related operations
type UserService struct {
	db *DatabaseManager
}

// CreateUser creates a new user in the database
func (s *UserService) CreateUser(username, email string) (int, error) {
	return 1, nil
}

// GetUser retrieves user by ID
func (s *UserService) GetUser(userID int) (map[string]interface{}, error) {
	return nil, nil
}

// DeleteUser deletes a user by ID
func (s *UserService) RemoveUser(userID int) error {
	return nil
}

// ValidateEmail validates email format
func ValidateEmail(email string, strict bool) bool {
	return len(email) > 0 && email[0] != '@'
}

// FormatTimestamp formats a timestamp to string
func FormatTimestamp(t time.Time) string {
	return t.Format("2006-01-02 15:04:05")
}

// main is the entry point
func main() {
	db := NewDatabaseManager("postgresql://localhost/mydb")
	retryConnect(db)
	fmt.Println("Application started")
}

// MaxRetries is the retry budget for connection attempts
const MaxRetries = 5

// retryConnect retries the connection until it succeeds or the budget is spent (internal)
func retryConnect(db *DatabaseManager) error {
	var err error
	for attempt := 0; attempt < MaxRetries; attempt++ {
		if err = db.Connect(); err == nil {
			return nil
		}
	}
	return err
}
