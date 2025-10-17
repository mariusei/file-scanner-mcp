/// <summary>
/// Example C# file for testing the scanner.
/// </summary>

using System;
using System.Collections.Generic;
using System.Linq;

namespace MyApp.Services
{
    /// <summary>
    /// Configuration interface for application settings.
    /// </summary>
    public interface IConfig
    {
        string ApiKey { get; }
        string Endpoint { get; }
        int Timeout { get; }
    }

    /// <summary>
    /// Manages database connections and queries.
    /// </summary>
    public class DatabaseManager
    {
        private string _connectionString;
        private object _connection;

        /// <summary>
        /// Constructs a new DatabaseManager with the given connection string.
        /// </summary>
        public DatabaseManager(string connectionString)
        {
            _connectionString = connectionString;
            _connection = null;
        }

        /// <summary>
        /// Gets or sets the connection string.
        /// </summary>
        public string ConnectionString
        {
            get => _connectionString;
            set => _connectionString = value;
        }

        /// <summary>
        /// Establishes a connection to the database.
        /// </summary>
        public void Connect()
        {
            Console.WriteLine($"Connecting to {_connectionString}");
        }

        /// <summary>
        /// Closes the database connection.
        /// </summary>
        public void Disconnect()
        {
            if (_connection != null)
            {
                Console.WriteLine("Disconnecting");
            }
        }

        /// <summary>
        /// Executes a SQL query and returns the results.
        /// </summary>
        public List<Dictionary<string, object>> Query(string sql)
        {
            return new List<Dictionary<string, object>>();
        }
    }

    /// <summary>
    /// Handles user-related operations.
    /// </summary>
    public class UserService
    {
        private DatabaseManager _db;

        /// <summary>
        /// Constructs a UserService with a database manager.
        /// </summary>
        public UserService(DatabaseManager db)
        {
            _db = db;
        }

        /// <summary>
        /// Gets the database manager.
        /// </summary>
        public DatabaseManager Database { get => _db; }

        /// <summary>
        /// Creates a new user in the system.
        /// </summary>
        public int CreateUser(string username, string email)
        {
            return 1;
        }

        /// <summary>
        /// Retrieves a user by their ID.
        /// </summary>
        public Dictionary<string, object>? GetUser(int userId)
        {
            return null;
        }

        /// <summary>
        /// Deletes a user from the system.
        /// </summary>
        public bool DeleteUser(int userId)
        {
            return true;
        }
    }

    /// <summary>
    /// Utility class for email validation.
    /// </summary>
    public static class EmailValidator
    {
        /// <summary>
        /// Validates an email address format.
        /// </summary>
        public static bool ValidateEmail(string email)
        {
            return email != null && email.Contains("@");
        }
    }

    /// <summary>
    /// Represents a point in 2D space.
    /// </summary>
    public struct Point
    {
        public double X { get; set; }
        public double Y { get; set; }

        /// <summary>
        /// Constructs a new point.
        /// </summary>
        public Point(double x, double y)
        {
            X = x;
            Y = y;
        }

        /// <summary>
        /// Calculates the distance from origin.
        /// </summary>
        public double DistanceFromOrigin()
        {
            return Math.Sqrt(X * X + Y * Y);
        }
    }

    /// <summary>
    /// User role enumeration.
    /// </summary>
    public enum UserRole
    {
        Admin,
        User,
        Guest
    }
}
