"""Generate a synthetic 'onboard camera' clip for validating the analysis pipeline.

The scene is a textured field that expands away from the focus of expansion to
simulate forward motion, with lateral shifts for cornering and slow-downs for
braking. It is not a real car, but it exercises the optical-flow proxies.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np


def make_clip(out: str, seconds: float = 20.0, fps: int = 30, size: tuple[int, int] = (640, 360)) -> Path:
    w, h = size
    rng = np.random.default_rng(7)

    grid = rng.integers(0, 255, size=(900, 1600, 3), dtype=np.uint8)
    for i in range(0, 900, 40):
        cv2.line(grid, (0, i), (1600, i), (255, 255, 255), 1)
    for j in range(0, 1600, 40):
        cv2.line(grid, (j, 0), (j, 900), (255, 255, 255), 1)
    gh, gw = grid.shape[:2]

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    cx, cy = gw / 2, gh / 2
    scale = 1.0
    pan = 0.0
    n = int(seconds * fps)
    for i in range(n):
        t = i / fps
        if 6.0 <= t < 8.0:
            rate = -0.02
        elif 8.0 <= t < 13.0:
            rate = 0.010
        else:
            rate = 0.006
        scale = float(np.clip(scale + rate, 0.4, 6.0))
        steer = np.sin(t * 1.2) * (0.0 if t < 13 else 1.0)
        pan += steer * 6.0

        m = np.array([[scale, 0, cx - scale * cx - pan], [0, scale, cy - scale * cy]], np.float32)
        warped = cv2.warpAffine(grid, m, (w, h), borderMode=cv2.BORDER_REFLECT)
        writer.write(warped)

    writer.release()
    return out_path


if __name__ == "__main__":
    path = make_clip(sys.argv[1] if len(sys.argv) > 1 else "sample.mp4")
    print(path)
