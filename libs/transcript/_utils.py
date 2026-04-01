"""Internal utilities for transcript processing."""

import subprocess
from typing import List


def run_command(cmd: List[str], capture: bool = True) -> str:
    """Execute a command and return its output."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return ""
        return result.stdout
    except subprocess.TimeoutExpired:
        return ""
    except Exception:
        return ""
