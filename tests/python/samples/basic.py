"""Example Python file for testing the scanner."""

import os
from pathlib import Path
from typing import Optional


class DatabaseManager:
    """Manages database connections and queries."""

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.connection = None

    def connect(self):
        """Establish database connection."""
        print(f"Connecting to {self.connection_string}")

    def disconnect(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()

    def query(self, sql: str) -> list:
        """Execute a SQL query."""
        return []


class UserService:
    """Handles user-related operations."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def create_user(self, username: str, email: str) -> int:
        """Create a new user."""
        return 1

    def get_user(self, user_id: int) -> Optional[dict]:
        """Retrieve user by ID."""
        return None

    def delete_user(self, user_id: int) -> bool:
        """Delete a user."""
        return True


def validate_email(email: str) -> bool:
    """Validate email format."""
    return "@" in email


def main():
    """Main entry point."""
    db = DatabaseManager("postgresql://localhost/mydb")
    service = UserService(db)
    print("Application started")


if __name__ == "__main__":
    main()
