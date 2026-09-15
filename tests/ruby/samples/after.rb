# Example Ruby file for testing the scanner

require 'json'
require 'net/http'
require_relative 'helpers'

# Data access layer module
module DataAccess
  # Manages database connections and queries
  class DatabaseManager
    attr_accessor :connection_string
    attr_reader :connection

    def initialize(connection_string)
      @connection_string = connection_string
      @connection = nil
    end

    # Establish database connection
    def connect
      puts "Connecting to #{@connection_string}"
    end

    # Execute a SQL query
    def query(sql)
      []
    end

    # Class method for creating a default instance
    def self.create_default
      new("postgresql://localhost/mydb")
    end
  end
end

# Handles user-related operations
class UserService
  def initialize(db)
    @db = db
  end

  # Create a new user
  def create_user(username, email)
    validate_email(email) ? 1 : 0
  end

  # Retrieve user by ID
  def get_user(user_id)
    nil
  end

  # Delete a user
  def remove_user(user_id)
    true
  end
end

# Validate email format
def validate_email(email, strict = false)
  email.include?('@')
end

# Liveness probe
def health
  { status: 'ok' }
end

# Default number of connection attempts
DEFAULT_ATTEMPTS = 5

# Retries a block a bounded number of times
class Retrier
  def initialize(attempts = DEFAULT_ATTEMPTS)
    @attempts = attempts
  end

  # Run the block until it returns true or the attempts are spent
  def run(&action)
    @attempts.times { return true if attempt(&action) }
    false
  end

  private

  # Execute one attempt (internal)
  def attempt
    yield == true
  end
end

# Main entry point
def main
  db = DataAccess::DatabaseManager.create_default
  service = UserService.new(db)
  Retrier.new.run { db.connect }
  puts "Application started"
end

main if __FILE__ == $PROGRAM_NAME
