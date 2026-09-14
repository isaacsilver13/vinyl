"""Run the Vinyl daily refresh job from any working directory.

Mirrors the production cron (see .github/workflows/app-daily-refresh.yml),
which runs `refresh_all.py --force` and lets it send alert emails inline.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("PROJECT_ROOT", str(DEFAULT_ROOT))).resolve()
PYTHON = os.environ.get("PYTHON", sys.executable)


def run(script: Path, *args: str) -> None:
    command = [PYTHON, str(script), *args]
    print("Running:", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    run(ROOT / "refresh_all.py", "--force")
    print("Daily refresh completed.")
