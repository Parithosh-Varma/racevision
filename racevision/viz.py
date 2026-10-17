from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .analyze import Config, Result


def plot(result: Result, out: str | Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = Path(out)
    if not result.samples:
        raise RuntimeError("no samples to plot")

    t = np.array([s.t for s in result.samples])
    speed = np.array([s.speed for s in result.samples])
    accel = np.array([s.accel for s in result.samples])
    lateral = np.array([s.lateral for s in result.samples])

    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    axes[0].plot(t, speed, color="#1f77b4")
    axes[0].set_ylabel("speed proxy")
    axes[1].plot(t, accel, color="#d62728")
    axes[1].axhline(0, color="gray", lw=0.7)
    axes[1].set_ylabel("accel proxy")
    axes[2].plot(t, lateral, color="#2ca02c")
    axes[2].axhline(0, color="gray", lw=0.7)
    axes[2].set_ylabel("lateral flow")
    axes[2].set_xlabel("time (s)")

    for ax in axes:
        for e in result.braking:
            ax.axvspan(e.t_start, e.t_end, color="red", alpha=0.15)
        for e in result.turns:
            ax.axvspan(e.t_start, e.t_end, color="blue", alpha=0.08)

    fig.suptitle("Driver behavior (optical-flow proxies)  |  red = braking, blue = cornering")
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def overlay(video: str | Path, result: Result, out: str | Path, cfg: Config | None = None) -> Path:
    cfg = cfg or result.cfg
    video = Path(video)
    out = Path(out)

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    times = np.array([s.t for s in result.samples]) if result.samples else np.array([])
    speed = np.array([s.speed for s in result.samples]) if result.samples else np.array([])
    braking = np.array([s.braking for s in result.samples]) if result.samples else np.array([])

    box_w, box_h = max(200, w // 3), max(80, h // 6)
    margin = 20

    idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t = idx / fps
            if times.size:
                k = int(np.argmin(np.abs(times - t)))
                s = result.samples[k]
                cv2.putText(frame, f"t={s.t:6.1f}s  speed={s.speed:5.2f}  lat={s.lateral:+5.2f}",
                            (margin, margin + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                if s.braking:
                    cv2.putText(frame, "BRAKE", (margin, margin + 56),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
                    cv2.rectangle(frame, (0, 0), (w - 1, h - 1), (0, 0, 255), 14)
                if s.turn_dir:
                    label = "TURN >" if s.turn_dir > 0 else "< TURN"
                    cv2.putText(frame, label, (w - 220, margin + 56),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 120, 0), 2)

                x0, y0 = margin, h - box_h - margin
                cv2.rectangle(frame, (x0, y0), (x0 + box_w, y0 + box_h), (0, 0, 0), -1)
                lo, hi = float(speed.min()), float(speed.max())
                span = max(1e-6, hi - lo)
                for k2 in range(len(times)):
                    if times[k2] > t:
                        break
                    px = x0 + int(box_w * (times[k2] / max(times[-1], 1e-6)))
                    py = y0 + box_h - int(box_h * (speed[k2] - lo) / span)
                    color = (0, 0, 255) if braking[k2] else (0, 255, 0)
                    cv2.circle(frame, (px, py), 1, color, -1)
            writer.write(frame)
            idx += 1
    finally:
        cap.release()
        writer.release()
    return out
