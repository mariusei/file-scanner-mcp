// Example C++ file for testing the scanner

#include <iostream>
#include <string>
#include <vector>
#include <memory>

// Utility namespace
namespace utils {

// Validate email format
bool validate_email(const std::string& email) {
    return email.find('@') != std::string::npos;
}

// Format user name
std::string format_name(const std::string& first, const std::string& last) {
    return first + " " + last;
}

} // namespace utils

// Database namespace
namespace database {

// Database manager class
class DatabaseManager {
private:
    std::string connection_string;
    bool connected;

public:
    // Constructor
    DatabaseManager(const std::string& conn_str)
        : connection_string(conn_str), connected(false) {}

    // Virtual destructor
    virtual ~DatabaseManager() {
        disconnect();
    }

    // Connect to database
    virtual bool connect() {
        std::cout << "Connecting to: " << connection_string << std::endl;
        connected = true;
        return true;
    }

    // Disconnect from database
    virtual void disconnect() {
        if (connected) {
            std::cout << "Disconnecting..." << std::endl;
            connected = false;
        }
    }

    // Check if connected
    bool is_connected() const {
        return connected;
    }

    // Execute query
    std::vector<std::string> query(const std::string& sql) const {
        return std::vector<std::string>();
    }
};

} // namespace database

// User service class
class UserService {
private:
    std::shared_ptr<database::DatabaseManager> db;
    int user_count;

public:
    // Constructor
    UserService(std::shared_ptr<database::DatabaseManager> database)
        : db(database), user_count(0) {}

    // Create a new user
    int create_user(const std::string& username, const std::string& email) {
        if (!utils::validate_email(email)) {
            return -1;
        }
        user_count++;
        return user_count;
    }

    // Get user by ID
    std::string get_user(int user_id) const {
        return "User" + std::to_string(user_id);
    }

    // Delete user
    bool delete_user(int user_id) {
        user_count--;
        return true;
    }

    // Static method to get service version
    static std::string get_version() {
        return "1.0.0";
    }

    // Get user count
    int get_user_count() const {
        return user_count;
    }
};

// Status enumeration
enum class Status {
    Success,
    Error,
    Pending
};

// Template function
template<typename T>
T max_value(T a, T b) {
    return (a > b) ? a : b;
}

// Main entry point
int main() {
    auto db = std::make_shared<database::DatabaseManager>("postgresql://localhost/mydb");
    UserService service(db);

    db->connect();

    int user_id = service.create_user("john_doe", "john@example.com");
    std::cout << "Created user: " << user_id << std::endl;

    std::cout << "Service version: " << UserService::get_version() << std::endl;

    return 0;
}
