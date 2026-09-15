/// Example Rust file for testing the scanner.

use std::collections::HashMap;
use std::fmt::Display;

/// User account with basic information.
#[derive(Debug, Clone)]
pub struct User {
    pub id: u64,
    pub name: String,
    email: String,
}

/// Database connection manager.
pub struct DatabaseManager {
    connection_string: String,
    pool: Option<String>,
}

impl DatabaseManager {
    /// Create a new database manager.
    pub fn new(connection_string: String) -> Self {
        Self {
            connection_string,
            pool: None,
        }
    }

    /// Connect to the database.
    pub fn connect(&mut self) -> Result<(), String> {
        println!("Connecting to {}", self.connection_string);
        Ok(())
    }
}

/// Service for user operations.
pub struct UserService {
    db: DatabaseManager,
}

impl UserService {
    /// Create a user.
    pub fn create_user(&self, name: String, email: String) -> Result<u64, String> {
        Ok(1)
    }

    /// Get user by ID.
    pub fn get_user(&self, user_id: u64) -> Option<User> {
        None
    }

    /// Delete a user.
    pub fn remove_user(&self, user_id: u64) -> bool {
        true
    }
}

/// Trait for objects that can be validated.
pub trait Validate {
    /// Validate the object.
    fn validate(&self) -> Result<(), String>;
}

impl Validate for User {
    fn validate(&self) -> Result<(), String> {
        if self.email.contains('@') {
            Ok(())
        } else {
            Err("Invalid email".to_string())
        }
    }
}

/// Validate an email address.
pub fn validate_email<S: AsRef<str>>(email: S) -> bool {
    email.as_ref().contains('@')
}

/// Entry point for the application.
fn main() {
    let mut db = DatabaseManager::new("postgresql://localhost/mydb".to_string());
    db.connect().unwrap();
    if validate_email("ada@example.com") {
        retry(&mut || db.connect().is_ok(), MAX_ATTEMPTS);
    }
    println!("Application started");
}

/// Liveness probe.
pub fn health() -> &'static str {
    "ok"
}

/// Upper bound on connection attempts.
pub const MAX_ATTEMPTS: u32 = 5;

/// Run `action` until it returns true or the attempts are spent (private).
fn retry(action: &mut dyn FnMut() -> bool, attempts: u32) -> bool {
    for _ in 0..attempts {
        if action() {
            return true;
        }
    }
    false
}
