// Example C++ header file for testing the scanner

#ifndef BASIC_H
#define BASIC_H

#include <string>
#include <vector>

// Forward declarations
class UserService;

namespace utils {

// Validate email format
bool validate_email(const std::string& email);

// Format user name
std::string format_name(const std::string& first, const std::string& last);

} // namespace utils

namespace database {

// Database connection interface
class IConnection {
public:
    virtual ~IConnection() = default;

    // Connect to database
    virtual bool connect() = 0;

    // Disconnect from database
    virtual void disconnect() = 0;

    // Check if connected
    virtual bool is_connected() const = 0;
};

// Database manager class declaration
class DatabaseManager : public IConnection {
private:
    std::string connection_string;
    bool connected;

public:
    // Constructor
    DatabaseManager(const std::string& conn_str);

    // Virtual destructor
    virtual ~DatabaseManager();

    // Connect to database
    virtual bool connect() override;

    // Disconnect from database
    virtual void disconnect() override;

    // Check if connected
    virtual bool is_connected() const override;

    // Execute query
    std::vector<std::string> query(const std::string& sql) const;
};

} // namespace database

// User data structure
struct UserData {
    int id;
    std::string username;
    std::string email;
    bool active;
};

// User service class declaration
class UserService {
private:
    database::DatabaseManager* db;
    int user_count;

public:
    // Constructor
    UserService(database::DatabaseManager* database);

    // Destructor
    ~UserService();

    // Create a new user
    int create_user(const std::string& username, const std::string& email);

    // Get user by ID
    std::string get_user(int user_id) const;

    // Delete user
    bool delete_user(int user_id);

    // Static method to get service version
    static std::string get_version();

    // Get user count
    int get_user_count() const;
};

// Status enumeration
enum class Status {
    Success,
    Error,
    Pending,
    Unknown
};

// Permission flags
enum Permission {
    PERM_READ = 1,
    PERM_WRITE = 2,
    PERM_EXECUTE = 4,
    PERM_DELETE = 8
};

// Template function declaration
template<typename T>
T max_value(T a, T b);

// Template class declaration
template<typename T>
class Container {
private:
    std::vector<T> items;

public:
    // Add item
    void add(const T& item);

    // Get item at index
    T get(size_t index) const;

    // Get size
    size_t size() const;
};

#endif // BASIC_H
