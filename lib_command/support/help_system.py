"""
Help System - Integrates OpenM Handbook into the REPL.

Loads and serves handbook content for interactive help.
"""

from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class HandbookSection:
    """A section of the handbook."""
    part: str                    # e.g., "01", "05", "20"
    title: str
    content: str
    topics: list[str]            # Searchable topics


class HandbookHelp:
    """
    Loads and serves handbook content for the REPL.
    """

    HANDBOOK_DIR = Path("./")

    # Mapping of common terms to handbook parts
    TOPIC_INDEX = {
        # Rules
        "rule": "01",
        "rule": "01",
        "cell rule": "01",
        "anchored rule": "01",
        "default item": "03",
        "rules": "03",
        "precedence": "03",
        "explanation": "03",

        # Sequential keywords
        "sequential": "05",
        "this": "05",
        "prev": "05",
        "next": "05",
        "first": "05",
        "last": "05",

        # Dynamic bounds
        "dynamic": "04",
        "bounds": "04",
        "range": "04",

        # Excel comparison
        "excel": "20",
        "comparison": "20",
        "switching": "20",

        # Calculation
        "calculation": "02",
        "engine": "02",
        "circular": "02",
        "recalc": "02",

        # Formatting
        "format": "formatting",
        "bold": "formatting",
        "color": "formatting",

        # Navigation
        "navigate": "navigation",
        "cursor": "navigation",
        "selection": "navigation",
    }

    def __init__(self):
        self._sections: dict[str, HandbookSection] = {}
        self._loaded = False

    def _load_handbook(self):
        """Lazy-load handbook content."""
        if self._loaded:
            return

        # Find all handbook files
        files = list(self.HANDBOOK_DIR.glob("Handbook_part_*.md"))

        for filepath in files:
            # Extract part number from filename
            match = re.search(r'Handbook_part_(\d+(?:\.\d+)?|Appendix_A)\.md', filepath.name)
            if not match:
                continue

            part = match.group(1)

            try:
                content = filepath.read_text(encoding='utf-8')
                # Extract title from first # line
                title_match = re.search(r'^# (.+)$', content, re.MULTILINE)
                title = title_match.group(1) if title_match else f"Part {part}"

                # Extract topics from content (headers, code blocks, etc.)
                topics = self._extract_topics(content)

                self._sections[part] = HandbookSection(
                    part=part,
                    title=title,
                    content=content,
                    topics=topics
                )
            except Exception:
                pass  # Skip files that can't be read

        self._loaded = True

    def _extract_topics(self, content: str) -> list[str]:
        """Extract searchable topics from content."""
        topics = []

        # Headers
        for match in re.finditer(r'^##+ (.+)$', content, re.MULTILINE):
            topics.append(match.group(1).lower())

        # Code examples
        for match in re.finditer(r'`([^`]+)`', content):
            topics.append(match.group(1).lower())

        # Bold terms
        for match in re.finditer(r'\*\*([^*]+)\*\*', content):
            topics.append(match.group(1).lower())

        return topics

    def list_parts(self) -> list[tuple[str, str]]:
        """List available handbook parts with titles."""
        self._load_handbook()
        return [(part, section.title) for part, section in sorted(self._sections.items())]

    def get_part(self, part: str) -> Optional[HandbookSection]:
        """Get a specific handbook part by number/ID."""
        self._load_handbook()
        return self._sections.get(part)

    def search(self, query: str) -> list[tuple[str, str, str]]:
        """
        Search handbook for query string.
        Returns list of (part, title, excerpt) tuples.
        """
        self._load_handbook()
        query = query.lower()
        results = []

        for part, section in self._sections.items():
            # Check if query in title or topics
            if query in section.title.lower() or any(query in t for t in section.topics):
                # Extract excerpt around first match
                excerpt = self._extract_excerpt(section.content, query)
                results.append((part, section.title, excerpt))

        return results

    def _extract_excerpt(self, content: str, query: str, context: int = 150) -> str:
        """Extract text excerpt around query match."""
        content_lower = content.lower()
        idx = content_lower.find(query.lower())
        if idx == -1:
            # Return first paragraph
            lines = content.split('\n')
            for line in lines[:10]:
                if line.strip() and not line.startswith('#'):
                    return line.strip()[:100] + "..."
            return ""

        start = max(0, idx - context)
        end = min(len(content), idx + len(query) + context)
        excerpt = content[start:end]

        # Clean up markdown
        excerpt = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', excerpt)  # Remove links
        excerpt = re.sub(r'`', '', excerpt)  # Remove backticks

        return excerpt.strip()

    def find_topic(self, topic: str) -> Optional[HandbookSection]:
        """Find handbook part for a given topic."""
        self._load_handbook()

        # Direct lookup in topic index
        topic_lower = topic.lower()
        if topic_lower in self.TOPIC_INDEX:
            part = self.TOPIC_INDEX[topic_lower]
            return self._sections.get(part)

        # Search for matching topic
        for part, section in self._sections.items():
            if any(topic_lower in t for t in section.topics):
                return section

        return None

    def get_cheatsheet(self) -> str:
        """Get a quick reference cheatsheet."""
        return """
╔══════════════════════════════════════════════════════════════════╗
║                    OM Core Quick Reference                       ║
╠══════════════════════════════════════════════════════════════════╣
║  RULE BASICS                                                     ║
║  ────────────────────────────────────────────────────────────────║
║  Rule:           Dim.Item = expression                           ║
║  Cell rule:      =expression (anchored to cell address)          ║
║  Reference:      [Dim.Item] or [Dim1.Item1, Dim2.Item2]          ║
║                                                                  ║
║  DEFAULT ITEMS                                                   ║
║  ────────────────────────────────────────────────────────────────║
║  When adding dimensions, rules automatically bind to the         ║
║  default item of each new dimension to preserve behavior.        ║
║                                                                  ║
║  SEQUENTIAL KEYWORDS (for seq dimensions)                        ║
║  ────────────────────────────────────────────────────────────────║
║  [Dim[THIS]]   - Current item                                    ║
║  [Dim[PREV]]   - Previous item                                   ║
║  [Dim[NEXT]]   - Next item                                       ║
║  [Dim[FIRST]]  - First item                                      ║
║  [Dim[LAST]]   - Last item                                       ║
║                                                                  ║
║  EXAMPLES                                                        ║
║  ────────────────────────────────────────────────────────────────║
║  Line.Total = [Line.A] + [Line.B]                                ║
║  Revenue = [Revenue[THIS]] / [Revenue[PREV]] - 1                 ║
║  IF([Quarter[THIS]]=[Quarter[FIRST]], [Year[PREV]], ...)         ║
║                                                                  ║
║  COMMANDS                                                        ║
║  ────────────────────────────────────────────────────────────────║
║  set <target> <property> <value>     Set properties              ║
║  navigate <direction> [amount]       Navigate grid               ║
║  recalc                              Recalculate                 ║
║  save [path]                         Save workspace              ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""


# Global instance
_help_instance: Optional[HandbookHelp] = None


def get_help() -> HandbookHelp:
    """Get the global handbook help instance."""
    global _help_instance
    if _help_instance is None:
        _help_instance = HandbookHelp()
    return _help_instance
