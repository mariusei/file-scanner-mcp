"""HTML code analyzer for extracting imports, entry points, and structure."""

import re
from pathlib import Path
from typing import Optional

from .base import BaseAnalyzer
from .models import ImportInfo, EntryPointInfo


class HTMLAnalyzer(BaseAnalyzer):
    """Analyzer for HTML source files (.html, .htm, .xhtml)."""

    @classmethod
    def get_extensions(cls) -> list[str]:
        """HTML file extensions."""
        return [".html", ".htm", ".xhtml"]

    @classmethod
    def get_language_name(cls) -> str:
        """Return language name."""
        return "HTML"

    @classmethod
    def get_priority(cls) -> int:
        """Standard priority."""
        return 10

    def should_analyze(self, file_path: str) -> bool:
        """
        Skip HTML files that should not be analyzed.

        - Skip minified HTML files
        - Skip generated/compiled files
        """
        filename = Path(file_path).name.lower()

        # Skip minified files
        if ".min." in filename:
            return False

        # Skip common generated patterns
        if any(pattern in filename for pattern in [
            ".generated.", ".compiled.", ".cache."
        ]):
            return False

        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """
        Identify low-value HTML files for inventory listing.

        Low-value files:
        - Very small files (likely stubs)
        - Common boilerplate files
        """
        filename = Path(file_path).name.lower()

        # Very small HTML files are likely stubs
        if size < 100:
            return True

        # Common boilerplate files
        if filename in ("404.html", "500.html", "error.html"):
            return True

        return super().is_low_value_for_inventory(file_path, size)

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract resource imports from HTML file.

        Patterns supported:
        - <link href="..."> (stylesheets, icons)
        - <script src="..."> (JavaScript files)
        - <img src="..."> (images)
        - <a href="..."> (local page links)
        - CSS @import in <style> blocks
        """
        imports = []

        # Pattern 1: <link href="...">
        link_pattern = r'<link[^>]+href=["\']([^"\']+)["\'][^>]*>'
        for match in re.finditer(link_pattern, content, re.IGNORECASE):
            href = match.group(1)
            line_num = content[:match.start()].count("\n") + 1

            # Determine link type from rel attribute
            rel_match = re.search(
                r'rel=["\']([^"\']+)["\']',
                match.group(0),
                re.IGNORECASE
            )
            rel = rel_match.group(1) if rel_match else "unknown"

            # Skip external URLs for import tracking
            if self._is_external_url(href):
                continue

            import_type = "stylesheet" if "stylesheet" in rel.lower() else (
                "icon" if "icon" in rel.lower() else "link"
            )

            imports.append(ImportInfo(
                source_file=file_path,
                target_module=href,
                line=line_num,
                import_type=import_type,
                imported_names=[],
            ))

        # Pattern 2: <script src="...">
        script_pattern = r'<script[^>]+src=["\']([^"\']+)["\'][^>]*>'
        for match in re.finditer(script_pattern, content, re.IGNORECASE):
            src = match.group(1)
            line_num = content[:match.start()].count("\n") + 1

            if self._is_external_url(src):
                continue

            imports.append(ImportInfo(
                source_file=file_path,
                target_module=src,
                line=line_num,
                import_type="script",
                imported_names=[],
            ))

        # Pattern 3: <img src="..."> (for asset tracking)
        img_pattern = r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>'
        for match in re.finditer(img_pattern, content, re.IGNORECASE):
            src = match.group(1)
            line_num = content[:match.start()].count("\n") + 1

            if self._is_external_url(src):
                continue

            # Only track local images
            imports.append(ImportInfo(
                source_file=file_path,
                target_module=src,
                line=line_num,
                import_type="image",
                imported_names=[],
            ))

        # Pattern 4: CSS @import in <style> blocks
        style_pattern = r'<style[^>]*>(.*?)</style>'
        for style_match in re.finditer(style_pattern, content, re.IGNORECASE | re.DOTALL):
            style_content = style_match.group(1)
            style_start = content[:style_match.start()].count("\n")

            import_pattern = r'@import\s+(?:url\(["\']?([^"\')\s]+)["\']?\)|["\']([^"\']+)["\'])'
            for import_match in re.finditer(import_pattern, style_content, re.IGNORECASE):
                url = import_match.group(1) or import_match.group(2)
                line_num = style_start + style_content[:import_match.start()].count("\n") + 1

                if not self._is_external_url(url):
                    imports.append(ImportInfo(
                        source_file=file_path,
                        target_module=url,
                        line=line_num,
                        import_type="css_import",
                        imported_names=[],
                    ))

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """
        Find entry points in HTML file.

        Entry points:
        - index.html files (main entry)
        - Files with <!DOCTYPE html>
        - Files with <html> root element
        """
        entry_points = []
        filename = Path(file_path).name.lower()

        # Check for index files (common entry points)
        if filename in ("index.html", "index.htm", "default.html", "default.htm"):
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="html_entry",
                name="index",
                line=1,
                framework="HTML",
            ))

        # Check for DOCTYPE (indicates complete HTML document)
        doctype_pattern = r'<!DOCTYPE\s+html'
        doctype_match = re.search(doctype_pattern, content, re.IGNORECASE)
        if doctype_match:
            line_num = content[:doctype_match.start()].count("\n") + 1
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="html_document",
                name="DOCTYPE html",
                line=line_num,
            ))

        # Check for meta viewport (indicates responsive web page)
        viewport_pattern = r'<meta[^>]+name=["\']viewport["\'][^>]*>'
        viewport_match = re.search(viewport_pattern, content, re.IGNORECASE)
        if viewport_match:
            line_num = content[:viewport_match.start()].count("\n") + 1
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="responsive_page",
                name="viewport meta",
                line=line_num,
            ))

        return entry_points

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify HTML file into architectural cluster.

        Enhanced classification with HTML-specific patterns.
        """
        # Use base implementation first
        cluster = super().classify_file(file_path, content)

        if cluster == "other":
            filename = Path(file_path).name.lower()

            # Check for index/entry pages
            if filename in ("index.html", "index.htm", "default.html"):
                return "entry_points"

            # Check for error pages
            if any(err in filename for err in ["404", "500", "error"]):
                return "utilities"

            # Check for template files
            if "template" in filename or "_partial" in filename:
                return "utilities"

            # Check for test/demo pages
            if any(pattern in filename for pattern in ["test", "demo", "example"]):
                return "tests"

        return cluster

    def _is_external_url(self, url: str) -> bool:
        """Check if a URL is external (not a local file reference)."""
        if not url:
            return True

        # Check for protocol prefixes
        if url.startswith(("http://", "https://", "//", "data:", "blob:")):
            return True

        # Check for CDN patterns
        if any(cdn in url.lower() for cdn in [
            "cdn.", "cdnjs.", "unpkg.com", "jsdelivr.net",
            "googleapis.com", "cloudflare.com"
        ]):
            return True

        return False
