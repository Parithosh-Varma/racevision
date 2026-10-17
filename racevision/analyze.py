from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np


@dataclass
class Config:
    sample_fps: float = 10.0
    width: int = 480
    top_cut: float = 0.15
    bottom_cut: float = 0.12
    side_cut: float = 0.12
    smooth_sec: float = 0.6
    brake_pct: float = 12.0
    turn_pct: float = 85.0
    min_event_sec: float = 0.35


@dataclass
class Sample:
    t: float
    speed: float
    accel: float
    lateral: float
    expansion: float
    braking: int
    turn_dir: int


@dataclass
class Event:
    kind: str
    t_start: float
    t_end: float
    duration: float
    peak: float


@dataclass
class Result:
    samples: list[Sample] = field(default_factory=list)
    braking: list[Event] = field(default_factory=list)
    turns: list[Event] = field(default_factory=list)
    cfg: Config = field(default_factory=Config)
    duration: float = 0.0
    mean_speed: float = 0.0


def _build_mask(w: int, h: int, cfg: Config) -> tuple[np.ndarray, float, float]:
    mask = np.zeros((h, w), bool)
    y0 = int(h * cfg.top_cut)
    y1 = int(h * (1.0 - cfg.bottom_cut))
    x0 = int(w * cfg.side_cut)
    x1 = int(w * (1.0 - cfg.side_cut))
    mask[y0:y1, x0:x1] = True
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    return mask, cx, cy


def _iter_frames(path: Path, sample_fps: float, width: int):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(fps / sample_fps)))
    idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                t = idx / fps
                h = max(1, int(frame.shape[0] * width / frame.shape[1]))
                small = cv2.resize(frame, (width, h), interpolation=cv2.INTER_AREA)
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                yield t, gray
            idx += 1
    finally:
        cap.release()


def _flow_features(
    prev: np.ndarray, cur: np.ndarray, mask: np.ndarray, cx: float, cy: float
) -> tuple[float, float, float]:
    flow = cv2.calcOpticalFlowFarneback(prev, cur, None, 0.5, 3, 21, 3, 5, 1.2, 0)
    dx_all = flow[..., 0][mask]
    dy_all = flow[..., 1][mask]
    if dx_all.size == 0:
        return 0.0, 0.0, 0.0
    speed = float(np.median(np.hypot(dx_all, dy_all)))
    lateral = float(np.median(dx_all))
    ys, xs = np.nonzero(mask)
    rx = xs.astype(np.float32) - cx
    ry = ys.astype(np.float32) - cy
    r = np.hypot(rx, ry)
    good = r > 1.0
    if good.any():
        radial = (dx_all[good] * rx[good] + dy_all[good] * ry[good]) / r[good]
        expansion = float(np.median(radial))
    else:
        expansion = 0.0
    return speed, lateral, expansion


def _smooth(a: np.ndarray, win: int) -> np.ndarray:
    win = max(1, int(win))
    if win <= 1 or a.size == 0:
        return a
    kernel = np.ones(win) / win
    return np.convolve(a, kernel, mode="same")


def _runs(flags: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    i = 0
    n = len(flags)
    while i < n:
        if flags[i]:
            j = i
            while j < n and flags[j]:
                j += 1
            if j - i >= min_len:
                runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


def analyze_video(path: str | Path, cfg: Config | None = None) -> Result:
    cfg = cfg or Config()
    path = Path(path)

    t_list: list[float] = []
    speed_list: list[float] = []
    lateral_list: list[float] = []
    expansion_list: list[float] = []

    mask = None
    cx = cy = 0.0
    prev = None
    for t, gray in _iter_frames(path, cfg.sample_fps, cfg.width):
        if mask is None:
            h, w = gray.shape
            mask, cx, cy = _build_mask(w, h, cfg)
        if prev is not None:
            speed, lateral, expansion = _flow_features(prev, gray, mask, cx, cy)
            t_list.append(t)
            speed_list.append(speed)
            lateral_list.append(lateral)
            expansion_list.append(expansion)
        prev = gray

    if not t_list:
        return Result(cfg=cfg)

    t = np.asarray(t_list, float)
    speed = _smooth(np.asarray(speed_list, float), cfg.smooth_sec * cfg.sample_fps)
    lateral = _smooth(np.asarray(lateral_list, float), cfg.smooth_sec * cfg.sample_fps)
    expansion = _smooth(np.asarray(expansion_list, float), cfg.smooth_sec * cfg.sample_fps)

    accel = np.gradient(speed, t) if t.size > 1 else np.zeros_like(speed)

    brake_thr = np.percentile(accel, cfg.brake_pct) if accel.size else 0.0
    turn_thr = np.percentile(np.abs(lateral), cfg.turn_pct) if lateral.size else 0.0
    braking_flags = accel <= brake_thr
    turn_flags = np.abs(lateral) >= turn_thr

    min_len = max(1, int(cfg.min_event_sec * cfg.sample_fps))

    braking_events = [
        Event("brake", float(t[i]), float(t[j - 1]), float(t[j - 1] - t[i]), float(accel[i:j].min()))
        for i, j in _runs(braking_flags, min_len)
    ]
    turn_events = [
        Event(
            "turn",
            float(t[i]),
            float(t[j - 1]),
            float(t[j - 1] - t[i]),
            float(lateral[i:j][np.argmax(np.abs(lateral[i:j]))]),
        )
        for i, j in _runs(turn_flags, min_len)
    ]

    samples = [
        Sample(
            t=float(t[k]),
            speed=float(speed[k]),
            accel=float(accel[k]),
            lateral=float(lateral[k]),
            expansion=float(expansion[k]),
            braking=int(braking_flags[k]),
            turn_dir=int(np.sign(lateral[k])) if turn_flags[k] else 0,
        )
        for k in range(len(t))
    ]

    return Result(
        samples=samples,
        braking=braking_events,
        turns=turn_events,
        cfg=cfg,
        duration=float(t[-1]),
        mean_speed=float(np.mean(speed)),
    )


def write_csv(result: Result, out: str | Path) -> Path:
    out = Path(out)
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["t", "speed", "accel", "lateral", "expansion", "braking", "turn_dir"])
        for s in result.samples:
            writer.writerow(
                [f"{s.t:.3f}", f"{s.speed:.4f}", f"{s.accel:.4f}", f"{s.lateral:.4f}",
                 f"{s.expansion:.4f}", s.braking, s.turn_dir]
            )
    return out


def write_events_csv(result: Result, out: str | Path) -> Path:
    out = Path(out)
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["kind", "t_start", "t_end", "duration", "peak"])
        for e in result.braking + result.turns:
            writer.writerow([e.kind, f"{e.t_start:.3f}", f"{e.t_end:.3f}",
                             f"{e.duration:.3f}", f"{e.peak:.4f}"])
    return out
