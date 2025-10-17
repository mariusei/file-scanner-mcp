"""Plain text scanner - simple example without tree-sitter dependency."""

from typing import Optional

from .base import BaseScanner, StructureNode


class TextScanner(BaseScanner):
    """Scanner for plain text files - shows how simple a scanner can be!"""

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".txt"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Plain Text"

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Extract structure from plain text files."""
        text = source_code.decode("utf-8", errors="ignore")
        lines = text.split("\n")

        structures = []
        current_section = None
        section_start = None
        paragraph_start = None
        in_paragraph = False

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Detect section headers (all caps lines)
            if stripped and stripped.isupper() and len(stripped) > 3:
                if current_section and section_start:
                    current_section.end_line = i - 1
                    structures.append(current_section)

                current_section = StructureNode(
                    type="section",
                    name=stripped[:50],  # Limit length
                    start_line=i,
                    end_line=i,
                    children=[]
                )
                section_start = i
                in_paragraph = False

            # Detect underlined headers (=== or ---)
            elif i > 1 and stripped and all(c in "=-" for c in stripped) and len(stripped) > 2:
                prev_line = lines[i - 2].strip()
                if prev_line and not prev_line.isupper():
                    if current_section and section_start:
                        current_section.end_line = i - 2
                        structures.append(current_section)

                    current_section = StructureNode(
                        type="section",
                        name=prev_line[:50],
                        start_line=i - 1,
                        end_line=i,
                        children=[]
                    )
                    section_start = i - 1
                    in_paragraph = False

            # Track paragraphs
            elif stripped:
                if not in_paragraph:
                    paragraph_start = i
                    in_paragraph = True
            else:
                # Empty line ends paragraph
                if in_paragraph and paragraph_start:
                    para_node = StructureNode(
                        type="paragraph",
                        name=f"paragraph ({paragraph_start}-{i-1})",
                        start_line=paragraph_start,
                        end_line=i - 1
                    )
                    if current_section:
                        current_section.children.append(para_node)
                        current_section.end_line = i - 1
                    else:
                        structures.append(para_node)
                    in_paragraph = False

        # Close last section/paragraph
        if current_section and section_start:
            current_section.end_line = len(lines)
            structures.append(current_section)
        elif in_paragraph and paragraph_start:
            para_node = StructureNode(
                type="paragraph",
                name=f"paragraph ({paragraph_start}-{len(lines)})",
                start_line=paragraph_start,
                end_line=len(lines)
            )
            structures.append(para_node)

        return structures
