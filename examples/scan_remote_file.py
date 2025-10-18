#!/usr/bin/env python3
"""
Example: Scanning remote file content without downloading to disk.

This demonstrates how to use scan_file_content to analyze files from
GitHub or other remote sources without saving them locally first.
"""

import sys
from pathlib import Path

# Add src to path for this example
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scantool.scanner import FileScanner
from scantool.formatter import TreeFormatter


def main():
    """Example of scanning remote content."""

    # Simulate fetching a file from GitHub (in practice, you'd use requests or urllib)
    # For this example, we'll use a simple Python file content
    remote_content = """
# Sample Python file from a remote source
from typing import Optional

class UserRepository:
    \"\"\"Repository for managing users.\"\"\"

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.connection = None

    def connect(self) -> bool:
        \"\"\"Establish database connection.\"\"\"
        # Connection logic here
        return True

    def get_user(self, user_id: int) -> Optional[dict]:
        \"\"\"Fetch user by ID.\"\"\"
        # Query logic here
        return None

    def create_user(self, username: str, email: str) -> int:
        \"\"\"Create a new user and return their ID.\"\"\"
        # Insert logic here
        return 1


def validate_email(email: str) -> bool:
    \"\"\"Validate email format.\"\"\"
    return "@" in email and "." in email
"""

    # Create scanner
    scanner = FileScanner()
    formatter = TreeFormatter(
        show_signatures=True,
        show_decorators=True,
        show_docstrings=True
    )

    # Scan the remote content
    print("Scanning remote file: user_repository.py")
    print("=" * 60)

    structures = scanner.scan_content(
        content=remote_content,
        filename="user_repository.py",  # Filename determines the parser
        include_metadata=True
    )

    if structures:
        # Format and display the results
        result = formatter.format("user_repository.py", structures)
        print(result)
    else:
        print("Failed to scan content")

    print("\n" + "=" * 60)
    print("\nKey benefits:")
    print("  ✓ No need to download files to disk")
    print("  ✓ Works with any content source (GitHub, APIs, etc.)")
    print("  ✓ Filename extension determines the parser")
    print("  ✓ Same rich structure analysis as local files")


if __name__ == "__main__":
    main()
