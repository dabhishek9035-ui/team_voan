"""Cross-platform verification entry point for the integrated Pratibimb repository (Members A, B, and C)."""
import subprocess
import sys


def main():
    commands = [
        [
            sys.executable, "-m", "compileall", "-q",
            "pratibimb", "scripts", "intake", "extraction", "cards",
            "dashboard", "standin", "eval", "export", "breakme", "tools",
        ],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
        [
            sys.executable, "-m", "pytest", "-q", "tests",
            "--ignore-glob=tests/test_0*.py",
            "--ignore=tests/test_10_api_and_calibration.py",
        ],
        [sys.executable, "tools/check_forbidden.py"],
    ]
    for command in commands:
        completed = subprocess.run(command)
        if completed.returncode:
            return completed.returncode
    print("ALL DAYS VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
