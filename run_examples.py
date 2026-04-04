"""
run_examples.py — Runs all example .luz files and reports pass/fail.

Usage:
    python run_examples.py           # runs examples/
    python run_examples.py examples/ # explicit folder
"""

import subprocess
import sys
import os
import re
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

EXAMPLES_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("examples")
TIMEOUT      = 10   # seconds per file
INTERPRETER  = [sys.executable, "main.py"]

# Patterns that indicate the interpreter itself crashed (Python-level bug).
# These appear without a [Line X] prefix because main.py wraps them in except.
CRASH_PATTERN = re.compile(
    r'^(AttributeError|TypeError|NameError|KeyError|IndexError'
    r'|ValueError|RecursionError|ZeroDivisionError|RuntimeError'
    r'|NotImplementedError|AssertionError): ',
    re.MULTILINE
)

# Patterns that indicate an unhandled Luz runtime error escaped attempt/rescue.
LUZ_ERROR_PATTERN = re.compile(
    r'^\[Line \d+',
    re.MULTILINE
)

# EOF from listen() — file is interactive and needs user input.
EOF_PATTERN = re.compile(r'EOFError: EOF when reading a line')

# ── Helpers ───────────────────────────────────────────────────────────────────

RESET  = "\033[0m"
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

def tag(color, text): return f"{color}{text}{RESET}"

def classify(output: str, returncode: int):
    """Return ('PASS'|'FAIL'|'CRASH'|'INTERACTIVE'|'TIMEOUT', detail)."""
    if returncode == -1:
        return "TIMEOUT", "exceeded time limit"
    if EOF_PATTERN.search(output):
        # May still have a real error before the EOF
        rest = output[:EOF_PATTERN.search(output).start()].strip()
        if CRASH_PATTERN.search(rest) or LUZ_ERROR_PATTERN.search(rest):
            return "FAIL", rest.splitlines()[-1] if rest.splitlines() else "error before EOF"
        return "INTERACTIVE", "uses listen() — needs user input"
    if CRASH_PATTERN.search(output):
        m = CRASH_PATTERN.search(output)
        line = output[m.start():].splitlines()[0]
        return "CRASH", line
    if LUZ_ERROR_PATTERN.search(output):
        m = LUZ_ERROR_PATTERN.search(output)
        line = output[m.start():].splitlines()[0]
        return "FAIL", line
    return "PASS", ""

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    files = sorted(EXAMPLES_DIR.glob("*.luz"))
    if not files:
        print(f"No .luz files found in '{EXAMPLES_DIR}'")
        sys.exit(1)

    results = {"PASS": [], "FAIL": [], "CRASH": [], "INTERACTIVE": [], "TIMEOUT": []}

    print(f"\n{BOLD}Running {len(files)} examples in '{EXAMPLES_DIR}'{RESET}\n")
    print(f"  {'File':<35} {'Status':<14} Detail")
    print(f"  {'-'*35} {'-'*14} {'-'*40}")

    for path in files:
        try:
            proc = subprocess.run(
                INTERPRETER + [str(path)],
                input="",
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
            )
            output   = proc.stdout + proc.stderr
            retcode  = proc.returncode
        except subprocess.TimeoutExpired:
            output  = ""
            retcode = -1

        status, detail = classify(output, retcode)
        results[status].append(path.name)

        if status == "PASS":
            symbol = tag(GREEN,  "PASS")
        elif status == "INTERACTIVE":
            symbol = tag(YELLOW, "INTERACTIVE")
        elif status == "TIMEOUT":
            symbol = tag(YELLOW, "TIMEOUT")
        else:
            symbol = tag(RED,    status)

        detail_str = tag(DIM, detail[:60]) if detail else ""
        print(f"  {path.name:<35} {symbol:<23} {detail_str}")

    # ── Summary ───────────────────────────────────────────────────────────────
    total   = len(files)
    passed  = len(results["PASS"])
    skipped = len(results["INTERACTIVE"]) + len(results["TIMEOUT"])
    failed  = len(results["FAIL"]) + len(results["CRASH"])

    print(f"\n{BOLD}{'-'*70}{RESET}")
    print(f"  {tag(GREEN, f'{passed} passed')}  "
          f"{tag(YELLOW, f'{skipped} skipped')}  "
          f"{tag(RED, f'{failed} failed')}  "
          f"(total: {total})")

    if results["FAIL"] or results["CRASH"]:
        print(f"\n{tag(RED, BOLD + 'Failed files:' + RESET)}")
        for name in results["FAIL"] + results["CRASH"]:
            print(f"  - {name}")

    print()
    sys.exit(1 if failed > 0 else 0)

if __name__ == "__main__":
    main()
