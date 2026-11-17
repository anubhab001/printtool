"""PyInstaller entry point for the CLI binary. Kept separate from
printtool/cli.py so PyInstaller analyzes a plain script (no relative
imports) against the installed `printtool` package.
"""

from printtool.cli import main

if __name__ == "__main__":
    main()
