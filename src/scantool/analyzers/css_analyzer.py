"""CSS code analyzer for extracting imports and structure."""

import re
from pathlib import Path
from typing import Optional

from .base import BaseAnalyzer
from .models import ImportInfo, EntryPointInfo


class CSSAnalyzer(BaseAnalyzer):
    """Analyzer for CSS source files (.css)."""

    @classmethod
    def get_extensions(cls) -> list[str]:
        """CSS file extensions."""
        return [".css"]

    @classmethod
    def get_language_name(cls) -> str:
        """Return language name."""
        return "CSS"

    @classmethod
    def get_priority(cls) -> int:
        """Standard priority."""
        return 10

    def should_analyze(self, file_path: str) -> bool:
        """
        Skip CSS files that should not be analyzed.

        - Skip minified CSS files
        - Skip source maps
        - Skip generated/compiled files
        """
        filename = Path(file_path).name.lower()

        # Skip minified files
        if ".min." in filename:
            return False

        # Skip source maps
        if filename.endswith(".map"):
            return False

        # Skip common generated patterns
        if any(pattern in filename for pattern in [
            ".generated.", ".compiled.", "bundle.", "chunk."
        ]):
            return False

        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """
        Identify low-value CSS files for inventory listing.

        Low-value files:
        - Very small files (likely stubs)
        - Vendor files
        """
        filename = Path(file_path).name.lower()

        # Very small CSS files
        if size < 50:
            return True

        # Vendor/third-party files
        if any(pattern in filename for pattern in [
            "vendor", "normalize", "reset", "bootstrap.min"
        ]):
            return True

        return super().is_low_value_for_inventory(file_path, size)

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract imports from CSS file.

        Patterns supported:
        - @import url("...")
        - @import "..."
        - url(...) references in properties
        """
        imports = []

        # Pattern 1: @import statements
        import_pattern = r'@import\s+(?:url\(["\']?([^"\')\s]+)["\']?\)|["\']([^"\']+)["\'])'
        for match in re.finditer(import_pattern, content, re.IGNORECASE):
            url = match.group(1) or match.group(2)
            line_num = content[:match.start()].count("\n") + 1

            if self._is_external_url(url):
                continue

            imports.append(ImportInfo(
                source_file=file_path,
                target_module=url,
                line=line_num,
                import_type="css_import",
                imported_names=[],
            ))

        # Pattern 2: url() references in properties (fonts, images, etc.)
        url_pattern = r'url\(["\']?([^"\')\s]+)["\']?\)'
        for match in re.finditer(url_pattern, content, re.IGNORECASE):
            url = match.group(1)
            line_num = content[:match.start()].count("\n") + 1

            # Skip data URIs and external URLs
            if url.startswith("data:") or self._is_external_url(url):
                continue

            # Determine asset type
            url_lower = url.lower()
            if any(ext in url_lower for ext in [".woff", ".woff2", ".ttf", ".otf", ".eot"]):
                import_type = "font"
            elif any(ext in url_lower for ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"]):
                import_type = "image"
            else:
                import_type = "asset"

            imports.append(ImportInfo(
                source_file=file_path,
                target_module=url,
                line=line_num,
                import_type=import_type,
                imported_names=[],
            ))

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """
        Find entry points in CSS file.

        Entry points:
        - Main stylesheets (main.css, styles.css, app.css)
        - Files with :root CSS variables
        """
        entry_points = []
        filename = Path(file_path).name.lower()

        # Check for main stylesheet files
        main_patterns = ["main.css", "styles.css", "style.css", "app.css", "global.css"]
        if filename in main_patterns:
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="main_stylesheet",
                name=filename,
                line=1,
                framework="CSS",
            ))

        # Check for :root with CSS variables
        root_pattern = r':root\s*\{([^}]+)\}'
        root_match = re.search(root_pattern, content, re.DOTALL)
        if root_match:
            line_num = content[:root_match.start()].count("\n") + 1
            # Count CSS variables
            var_count = root_match.group(1).count("--")
            if var_count > 0:
                entry_points.append(EntryPointInfo(
                    file=file_path,
                    type="css_variables",
                    name=f":root ({var_count} variables)",
                    line=line_num,
                ))

        return entry_points

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify CSS file into architectural cluster.

        Enhanced classification with CSS-specific patterns.
        """
        # Use base implementation first
        cluster = super().classify_file(file_path, content)

        if cluster == "other":
            filename = Path(file_path).name.lower()

            # Check for main stylesheets
            if any(pattern in filename for pattern in ["main", "styles", "app", "global"]):
                return "entry_points"

            # Check for utility/helper stylesheets
            if any(pattern in filename for pattern in [
                "utils", "utility", "helpers", "mixins", "variables"
            ]):
                return "utilities"

            # Check for component stylesheets
            if any(pattern in filename for pattern in [
                "component", "button", "card", "modal", "form"
            ]):
                return "core_logic"

            # Check for reset/normalize
            if any(pattern in filename for pattern in ["reset", "normalize", "base"]):
                return "utilities"

        return cluster

    def _is_external_url(self, url: str) -> bool:
        """Check if a URL is external (not a local file reference)."""
        if not url:
            return True

        # Check for protocol prefixes
        if url.startswith(("http://", "https://", "//", "data:", "blob:")):
            return True

        return False
