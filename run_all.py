"""Cross-platform verification entry point for the complete Member B package."""
import subprocess
import sys


def main():
    commands = [
        [sys.executable, "-m", "compileall", "-q", "pratibimb", "scripts"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
    ]
    for command in commands:
        completed = subprocess.run(command)
        if completed.returncode:
            return completed.returncode
    print("ALL DAYS VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
