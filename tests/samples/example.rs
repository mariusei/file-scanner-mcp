// Example Rust file for testing the scanner

use std::collections::HashMap;
use std::fmt;
use std::error::Error;

#[derive(Debug, Clone)]
pub struct User {
    pub id: u64,
    pub username: String,
    pub email: String,
}

#[derive(Debug)]
pub enum UserError {
    NotFound,
    InvalidEmail,
    DatabaseError(String),
}

impl fmt::Display for UserError {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            UserError::NotFound => write!(f, "User not found"),
            UserError::InvalidEmail => write!(f, "Invalid email"),
            UserError::DatabaseError(msg) => write!(f, "Database error: {}", msg),
        }
    }
}

impl Error for UserError {}

pub trait UserRepository {
    fn find_by_id(&self, id: u64) -> Result<User, UserError>;
    fn save(&mut self, user: User) -> Result<(), UserError>;
    fn delete(&mut self, id: u64) -> Result<(), UserError>;
}

pub struct InMemoryUserRepository {
    users: HashMap<u64, User>,
    next_id: u64,
}

impl InMemoryUserRepository {
    pub fn new() -> Self {
        Self {
            users: HashMap::new(),
            next_id: 1,
        }
    }

    pub fn len(&self) -> usize {
        self.users.len()
    }
}

impl UserRepository for InMemoryUserRepository {
    fn find_by_id(&self, id: u64) -> Result<User, UserError> {
        self.users.get(&id).cloned().ok_or(UserError::NotFound)
    }

    fn save(&mut self, user: User) -> Result<(), UserError> {
        self.users.insert(user.id, user);
        Ok(())
    }

    fn delete(&mut self, id: u64) -> Result<(), UserError> {
        self.users.remove(&id).ok_or(UserError::NotFound)?;
        Ok(())
    }
}

pub fn validate_email(email: &str) -> bool {
    email.contains('@') && email.contains('.')
}

pub fn create_user(username: String, email: String) -> Result<User, UserError> {
    if !validate_email(&email) {
        return Err(UserError::InvalidEmail);
    }

    Ok(User {
        id: 0,
        username,
        email,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_validate_email() {
        assert!(validate_email("test@example.com"));
        assert!(!validate_email("invalid"));
    }
}
