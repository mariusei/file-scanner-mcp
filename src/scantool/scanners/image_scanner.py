"""Image file scanner - extracts metadata, dimensions, colors, and optimization hints."""

from io import BytesIO
from typing import Optional
from collections import Counter

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

from .base import BaseScanner, StructureNode


class ImageScanner(BaseScanner):
    """Fast image metadata scanner - no tree-sitter needed."""

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Image"

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Extract image metadata and visual characteristics."""
        if not PILLOW_AVAILABLE:
            return [StructureNode(
                type="error",
                name="PIL/Pillow not installed - cannot analyze images",
                start_line=1,
                end_line=1
            )]

        try:
            img = Image.open(BytesIO(source_code))
            structures = []

            # Basic format information
            structures.append(StructureNode(
                type="format",
                name=f"{img.format} - {img.mode}",
                start_line=1,
                end_line=1,
                docstring=f"Format: {img.format}, Color mode: {img.mode}"
            ))

            # Dimensions and aspect ratio
            width, height = img.size
            aspect_ratio = self._calculate_aspect_ratio(width, height)
            structures.append(StructureNode(
                type="dimensions",
                name=f"{width}×{height}",
                start_line=1,
                end_line=1,
                docstring=f"Aspect ratio: {aspect_ratio}"
            ))

            # Content type inference
            content_type = self._infer_content_type(img)
            structures.append(StructureNode(
                type="content-type",
                name=content_type,
                start_line=1,
                end_line=1,
                docstring="Inferred based on size and format"
            ))

            # Color analysis (for RGB/RGBA images)
            if img.mode in ('RGB', 'RGBA'):
                try:
                    colors = self._get_dominant_colors(img, n=3)
                    structures.append(StructureNode(
                        type="colors",
                        name="palette",
                        start_line=1,
                        end_line=1,
                        children=[
                            StructureNode(
                                type="color",
                                name=color,
                                start_line=1,
                                end_line=1
                            ) for color in colors
                        ]
                    ))
                except Exception as e:
                    if self.show_errors:
                        structures.append(StructureNode(
                            type="error",
                            name=f"Color analysis failed: {str(e)}",
                            start_line=1,
                            end_line=1
                        ))

            # Transparency check
            if img.mode in ('RGBA', 'LA', 'PA'):
                structures.append(StructureNode(
                    type="transparency",
                    name="has alpha channel",
                    start_line=1,
                    end_line=1
                ))

            # Animation frames (for GIF)
            if hasattr(img, 'n_frames') and img.n_frames > 1:
                structures.append(StructureNode(
                    type="animation",
                    name=f"{img.n_frames} frames",
                    start_line=1,
                    end_line=1
                ))

            # Optimization hints
            hints = self._get_optimization_hints(img, len(source_code))
            if hints:
                structures.append(StructureNode(
                    type="optimization",
                    name="suggestions",
                    start_line=1,
                    end_line=1,
                    children=[
                        StructureNode(
                            type="hint",
                            name=hint,
                            start_line=1,
                            end_line=1
                        ) for hint in hints
                    ]
                ))

            return structures

        except Exception as e:
            return [StructureNode(
                type="error",
                name=f"Failed to parse image: {str(e)}",
                start_line=1,
                end_line=1
            )]

    def _calculate_aspect_ratio(self, width: int, height: int) -> str:
        """Calculate and format aspect ratio."""
        if width == height:
            return "1:1 (square)"

        # Common aspect ratios
        ratio = width / height
        if abs(ratio - 16/9) < 0.1:
            return "16:9 (widescreen)"
        elif abs(ratio - 4/3) < 0.1:
            return "4:3 (standard)"
        elif abs(ratio - 21/9) < 0.1:
            return "21:9 (ultrawide)"
        elif abs(ratio - 3/2) < 0.1:
            return "3:2 (photo)"
        elif ratio > 1:
            return f"{ratio:.2f}:1 (landscape)"
        else:
            return f"1:{1/ratio:.2f} (portrait)"

    def _infer_content_type(self, img: Image.Image) -> str:
        """Infer content type based on characteristics."""
        width, height = img.size
        max_dim = max(width, height)

        # Icon detection
        if max_dim <= 128:
            return "icon"

        # Logo detection (small-medium with transparency)
        if img.mode in ('RGBA', 'LA', 'PA') and max_dim <= 512:
            return "logo"

        # Screenshot detection (specific ratios, medium-large)
        ratio = width / height
        if max_dim >= 800 and (abs(ratio - 16/9) < 0.1 or abs(ratio - 4/3) < 0.1):
            return "screenshot"

        # Photo detection (large JPEG)
        if img.format == 'JPEG' and max_dim >= 1000:
            return "photo"

        # Diagram/chart (medium size, limited colors)
        if 200 <= max_dim <= 1000:
            return "diagram/chart"

        return "image"

    def _get_dominant_colors(self, img: Image.Image, n: int = 3) -> list[str]:
        """Extract dominant colors from image (fast quantization)."""
        # Resize for performance
        img_small = img.copy()
        img_small.thumbnail((100, 100))

        # Convert to RGB if needed
        if img_small.mode != 'RGB':
            img_small = img_small.convert('RGB')

        # Get pixel colors
        pixels = list(img_small.getdata())

        # Count colors and get most common
        color_counts = Counter(pixels)
        dominant = color_counts.most_common(n)

        # Convert to hex
        return [f"#{r:02x}{g:02x}{b:02x}" for (r, g, b), _ in dominant]

    def _get_optimization_hints(self, img: Image.Image, file_size: int) -> list[str]:
        """Provide optimization suggestions."""
        hints = []
        width, height = img.size

        # Large PNG that could be JPEG
        if img.format == 'PNG' and img.mode == 'RGB' and file_size > 500_000:
            hints.append("Consider converting to JPEG (no transparency needed)")

        # Unused alpha channel
        if img.mode == 'RGBA':
            # Check if alpha is actually used (simple check)
            alpha = img.split()[-1]
            if alpha.getextrema()[0] == alpha.getextrema()[1] == 255:
                hints.append("Alpha channel unused - consider converting to RGB")

        # Oversized dimensions
        if max(width, height) > 3000:
            hints.append(f"Very large dimensions ({width}×{height}) - consider resizing for web")

        # Large file size
        if file_size > 2_000_000:
            size_mb = file_size / (1024 * 1024)
            hints.append(f"Large file size ({size_mb:.1f}MB) - consider compression")

        # WebP suggestion for photos
        if img.format == 'JPEG' and file_size > 100_000:
            hints.append("Consider WebP format for better compression")

        return hints
