"""Integration tests for the SOL26 interpreter.

Author: Jakub Glončák <xgloncj00@stud.fit.vut.cz>

Each *.test file in tests/integration/ has the format:

    +++<category>
    ***<description>
    !I! <exit_code>   (for successful runs, exit 0)
    OR
    !E! <exit_code>   (for expected runtime/static errors)

    <?xml ...>        (SOL26 XML input fed to stdin)

If a matching *.out file exists, stdout is also compared.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from conftest import INTERPRETER, collect_test_cases, parse_test_file

_CASES = collect_test_cases()


@pytest.mark.parametrize(
    "name,test_path",
    _CASES,
    ids=[c[0] for c in _CASES],
)
def test_integration(name: str, test_path: Path) -> None:
    """Run a single SOL26 integration test and check exit code + stdout."""
    expected_exit, xml_input = parse_test_file(test_path)

    result = subprocess.run(
        [sys.executable, str(INTERPRETER)],
        input=xml_input,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == expected_exit, (
        f"Exit code mismatch:\n"
        f"  expected : {expected_exit}\n"
        f"  actual   : {result.returncode}\n"
        f"  stderr   : {result.stderr.strip()}"
    )

    out_file = test_path.with_suffix(".out")
    if out_file.exists():
        expected_out = out_file.read_text(encoding="utf-8")
        assert result.stdout == expected_out, (
            f"Stdout mismatch:\n"
            f"  expected : {expected_out!r}\n"
            f"  actual   : {result.stdout!r}"
        )
