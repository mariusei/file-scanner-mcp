"""Expand bash-style brace patterns in glob expressions."""

import re
from typing import List


def expand_braces(pattern: str) -> List[str]:
    """
    Expand brace expressions in a glob pattern.

    Converts patterns like "**/*.{py,js,ts}" into multiple patterns:
    ["**/*.py", "**/*.js", "**/*.ts"]

    Args:
        pattern: Glob pattern potentially containing brace expressions

    Returns:
        List of expanded patterns (single item if no braces)

    Examples:
        expand_braces("**/*.{py,js}") → ["**/*.py", "**/*.js"]
        expand_braces("src/**/*.{ts,tsx}") → ["src/**/*.ts", "src/**/*.tsx"]
        expand_braces("**/*.py") → ["**/*.py"]
    """
    # Find brace expressions: {option1,option2,option3}
    brace_pattern = r'\{([^}]+)\}'
    match = re.search(brace_pattern, pattern)

    if not match:
        # No braces, return as-is
        return [pattern]

    # Extract the options inside braces
    options_str = match.group(1)
    options = [opt.strip() for opt in options_str.split(',')]

    # Get the parts before and after the braces
    before = pattern[:match.start()]
    after = pattern[match.end():]

    # Generate patterns for each option
    expanded = []
    for option in options:
        new_pattern = f"{before}{option}{after}"
        # Recursively expand in case there are more braces
        expanded.extend(expand_braces(new_pattern))

    return expanded
