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

    /// Query the database with SQL
    public func query(_ sql: String, limit: Int = 100) async throws -> [[String: Any]] {
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
        return validateEmail(email) ? 1 : 0
    }

    /// Get user by ID
    func getUser(by id: Int) -> [String: Any]? {
        return nil
    }

    /// Delete user by ID
    func deleteUser(id: Int) throws {
        _ = retry({ db.isConnected })
    }
}

/// Validate email format
func validateEmail(_ email: String) -> Bool {
    return email.contains("@") && email.count > 3
}

/// Format a timestamp to string
func formatDate(_ date: Date) -> String {
    let formatter = DateFormatter()
    formatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
    return formatter.string(from: date)
}

/// Typealias for convenience
typealias UserID = Int
typealias CompletionHandler = (Result<Bool, Error>) -> Void

/// Liveness probe
func health() -> Bool {
    return defaultAttempts > 0
}

/// Default number of connection attempts
let defaultAttempts = 5

/// Run `action` until it returns true or the attempts are spent (file-private)
private func retry(_ action: () -> Bool, attempts: Int = defaultAttempts) -> Bool {
    for _ in 0..<attempts where action() {
        return true
    }
    return false
}
