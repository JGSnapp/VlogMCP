from __future__ import annotations

from pathlib import Path

from mss import mss


def make_screenshot(output_path: str, monitor_index: int = 1) -> str:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with mss() as sct:
        sct.shot(mon=monitor_index, output=str(output))
    return str(output)
