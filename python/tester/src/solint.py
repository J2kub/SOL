#!/usr/bin/env python3
"""
Wrapper script for SOL26 interpreter - used by the integration testing framework.

This script provides a simple interface that:
1. Takes exactly one positional argument: the path to a SOL26 source file
2. Runs the interpreter on that file
3. Outputs the result to stdout

Author: Jakub Glončák <xgloncj00@stud.fit.vut.cz>
"""

import sys
import subprocess
from pathlib import Path


def main() -> int:
    """Main entry point for the SOL26 interpreter wrapper."""
    # Check argument count
    if len(sys.argv) != 2:
        print("Exactly one positional argument (source file path) is required.", file=sys.stderr)
        return 2
    
    # Get the source file path
    source_file = Path(sys.argv[1])
    
    # Check if the file exists
    if not source_file.exists():
        print(f"Error: Source file '{source_file}' does not exist.", file=sys.stderr)
        return 2
    
    # Get the path to the actual interpreter
    # The tester wrapper is at: python/tester/src/solint.py
    # The real interpreter is at: python/int/src/solint.py
    script_dir = Path(__file__).parent
    interpreter_path = script_dir / "../../../int/src/solint.py"
    interpreter_path = interpreter_path.resolve()
    
    # Run the interpreter with the source file
    try:
        result = subprocess.run(
            [sys.executable, str(interpreter_path), "--input", str(source_file)],
            capture_output=False,  # Let output go to stdout/stderr directly
            text=True
        )
        return result.returncode
    except Exception as e:
        print(f"Error running interpreter: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
