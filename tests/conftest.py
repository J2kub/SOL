"""Pytest integration test runner for SOL26 interpreter.

Author: Jakub Glončák <xgloncj00@stud.fit.vut.cz>

Each *.test file in tests/integration/ has the format:

    +++<category>
    ***<description>
    !I! <exit_code>   (for successful runs)
    OR
    !E! <exit_code>   (for expected errors)

    <?xml ...>        (SOL26 XML input)

If a matching *.out file exists, stdout is compared as well.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

INTERPRETER = Path(__file__).parent.parent / "python" / "int" / "src" / "solint.py"
TESTS_DIR = Path(__file__).parent / "integration"


def _parse_test_file(path: Path) -> tuple[int, str]:
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


def _collect_tests() -> list[tuple[str, Path]]:
    """Collect all *.test files and return (id, path) pairs."""
    return [
        (p.stem, p)
        for p in sorted(TESTS_DIR.glob("*.test"))
    ]


@pytest.mark.parametrize("name,test_path", _collect_tests(), ids=[t[0] for t in _collect_tests()])
def test_integration(name: str, test_path: Path) -> None:
    """Run a single SOL26 integration test."""
    expected_exit, xml_input = _parse_test_file(test_path)

    result = subprocess.run(
        [sys.executable, str(INTERPRETER)],
        input=xml_input,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == expected_exit, (
        f"Exit code mismatch for {name}:\n"
        f"  expected : {expected_exit}\n"
        f"  actual   : {result.returncode}\n"
        f"  stderr   : {result.stderr.strip()}"
    )

    out_file = test_path.with_suffix(".out")
    if out_file.exists():
        expected_out = out_file.read_text(encoding="utf-8")
        assert result.stdout == expected_out, (
            f"Stdout mismatch for {name}:\n"
            f"  expected : {expected_out!r}\n"
            f"  actual   : {result.stdout!r}"
        )
