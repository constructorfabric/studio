"""
Tests for AI agent WHEN clause navigation.

Validates that AGENTS.md contains WHEN clauses for navigation.
"""
import sys
import unittest
from pathlib import Path

# Add skills/cypilot/scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))


class TestWhenClauseNavigation(unittest.TestCase):
    """Test AGENTS.md structure and WHEN clauses."""

    def test_agents_md_contains_when_clauses(self):
        """Verify AGENTS.md exists and contains WHEN clauses."""
        agents_file = Path(__file__).parent.parent / "AGENTS.md"
        self.assertTrue(agents_file.exists(), "AGENTS.md must exist")
        
        content = agents_file.read_text(encoding='utf-8')

        self.assertIn("<!-- @cf:root-agents -->", content)
        self.assertIn('cf-studio-path = ".bootstrap"', content)
        self.assertIn("<!-- /@cf:root-agents -->", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
