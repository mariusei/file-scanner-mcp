// Basic Swift sample file for testing

import Foundation
import UIKit

/// Configuration structure for the application
struct Config {
    let host: String
    let port: Int
    var isEnabled: Bool = true
}

/// Protocol for logging operations
protocol Logger {
    /// Log a message
    func log(message: String)

    /// Log an error
    func logError(_ error: Error)
}

/// Enum representing user status
enum UserStatus: String {
    case active
    case inactive
    case pending

    /// Get display name for status
    var displayName: String {
        switch self {
        case .active: return "Active"
        case .inactive: return "Inactive"
        case .pending: return "Pending"
        }
    }
}

/// Database manager class for handling connections
public class DatabaseManager {
    private var connectionString: String
    private(set) var isConnected: Bool = false

    /// Initialize with connection string
    public init(connectionString: String) {
        self.connectionString = connectionString
    }

    /// Connect to the database
    public func connect() throws {
        print("Connecting to database")
        isConnected = true
    }

    /// Disconnect from database
    public func disconnect() {
        if isConnected {
            print("Disconnecting from database")
            isConnected = false
        }
    }

    /// Query the database with SQL
    public func query(_ sql: String) async throws -> [[String: Any]] {
        return []
    }
}

/// Extension adding logging capability to DatabaseManager
extension DatabaseManager: Logger {
    func log(message: String) {
        print("[DB] \(message)")
    }

    func logError(_ error: Error) {
        print("[DB ERROR] \(error.localizedDescription)")
    }
}

/// User service for handling user operations
class UserService {
    private let db: DatabaseManager

    init(db: DatabaseManager) {
        self.db = db
    }

    /// Create a new user
    func createUser(username: String, email: String) -> Int {
        return 1
    }

    /// Get user by ID
    func getUser(by id: Int) -> [String: Any]? {
        return nil
    }

    /// Delete user by ID
    func deleteUser(id: Int) throws {
        // Implementation
    }
}

/// Validate email format
func validateEmail(_ email: String) -> Bool {
    return email.contains("@") && email.count > 3
}

/// Format a timestamp to string
func formatTimestamp(_ date: Date) -> String {
    let formatter = DateFormatter()
    formatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
    return formatter.string(from: date)
}

/// Typealias for convenience
typealias UserID = Int
typealias CompletionHandler = (Result<Bool, Error>) -> Void
