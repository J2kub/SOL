"""Shared pytest fixtures and helpers for SOL26 integration tests.

Author: Jakub Glončák <xgloncj00@stud.fit.vut.cz>
"""

from __future__ import annotations

from pathlib import Path


INTERPRETER = Path(__file__).parent.parent / "python" / "int" / "src" / "solint.py"
TESTS_DIR = Path(__file__).parent / "integration"


def parse_test_file(path: Path) -> tuple[int, str]:
    """Return (expected_exit_code, xml_input) from a .test file."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    expected_exit = 0
    xml_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("!I!") or stripped.startswith("!E!"):
            expected_exit = int(stripped.split()[1])
        if stripped.startswith("<?xml"):
            xml_start = i
            break

    xml_input = "".join(lines[xml_start:])
    return expected_exit, xml_input


def collect_test_cases() -> list[tuple[str, Path]]:
    """Collect all *.test files and return (id, path) pairs."""
    return [(p.stem, p) for p in sorted(TESTS_DIR.glob("*.test"))]
