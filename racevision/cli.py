from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__
from .analyze import Config, analyze_video, write_csv, write_events_csv
from .capture import capture, probe
from . import viz


def _add_auth(p: argparse.ArgumentParser) -> None:
    p.add_argument("--cookies", help="path to a Netscape cookies.txt file")
    p.add_argument("--cookies-from-browser", help="e.g. chrome, firefox, edge, brave")


def _add_network(p: argparse.ArgumentParser) -> None:
    p.add_argument("-4", "--ipv4", action="store_true", help="force IPv4 (fixes googlevideo 403)")
    p.add_argument("-6", "--ipv6", action="store_true", help="force IPv6")
    p.add_argument("--ytdlp-arg", dest="ytdlp_args", action="append", default=[],
                   metavar="ARG", help="extra raw yt-dlp argument (repeatable)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="racevision", description="Collect race data from stream URLs")
    p.add_argument("--version", action="version", version=f"racevision {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("capture", help="download or record a stream to a local video")
    pc.add_argument("url")
    pc.add_argument("-o", "--out", required=True)
    pc.add_argument("--seconds", type=float, help="max duration to record/download")
    pc.add_argument("--start", type=float, help="section start (seconds)")
    pc.add_argument("--end", type=float, help="section end (seconds)")
    pc.add_argument("--quality", type=int, default=720)
    pc.add_argument("--format", dest="format", help="override yt-dlp -f format selector")
    pc.add_argument("--no-audio", action="store_true", help="video only; avoids live audio muxing (no ffmpeg network fetch)")
    pc.add_argument("--extractor-args", action="append", default=[], metavar="ARGS",
                    help="yt-dlp --extractor-args value, e.g. 'youtube:player_client=tv' (repeatable)")
    pc.add_argument("--downloader-args", action="append", default=[], metavar="ARGS",
                    help="yt-dlp --downloader-args value (repeatable)")
    _add_auth(pc)
    _add_network(pc)

    pp = sub.add_parser("probe", help="print stream metadata as JSON")
    pp.add_argument("url")
    _add_auth(pp)
    _add_network(pp)

    pa = sub.add_parser("analyze", help="driver-behavior analysis of a POV video")
    pa.add_argument("video")
    pa.add_argument("-o", "--out", help="output CSV (default: <video>.csv)")
    pa.add_argument("--events", help="output events CSV (default: <video>.events.csv)")
    pa.add_argument("--plot", help="output PNG plot")
    pa.add_argument("--overlay", help="output annotated MP4")
    pa.add_argument("--sample-fps", type=float, default=10.0)
    pa.add_argument("--width", type=int, default=480)
    pa.add_argument("--top-cut", type=float, default=0.15)
    pa.add_argument("--bottom-cut", type=float, default=0.12)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.cmd == "probe":
        info = probe(args.url, args.cookies, args.cookies_from_browser,
                     args.ytdlp_args, args.ipv4, args.ipv6)
        print(json.dumps(info.__dict__, indent=2))

    elif args.cmd == "capture":
        extra = list(args.ytdlp_args)
        for v in args.extractor_args:
            extra += ["--extractor-args", v]
        for v in args.downloader_args:
            extra += ["--downloader-args", v]
        path = capture(
            args.url,
            args.out,
            seconds=args.seconds,
            start=args.start,
            end=args.end,
            quality=args.quality,
            cookies=args.cookies,
            cookies_from_browser=args.cookies_from_browser,
            fmt=args.format,
            no_audio=args.no_audio,
            extra_args=extra,
            ipv4=args.ipv4,
            ipv6=args.ipv6,
        )
        print(f"saved: {path}")

    elif args.cmd == "analyze":
        cfg = Config(
            sample_fps=args.sample_fps,
            width=args.width,
            top_cut=args.top_cut,
            bottom_cut=args.bottom_cut,
        )
        result = analyze_video(args.video, cfg)
        video = Path(args.video)
        out = Path(args.out) if args.out else video.with_suffix(".csv")
        write_csv(result, out)
        events = Path(args.events) if args.events else video.with_suffix(".events.csv")
        write_events_csv(result, events)
        print(f"samples : {len(result.samples)} -> {out}")
        print(f"duration: {result.duration:.1f}s")
        print(f"braking : {len(result.braking)} events -> {events}")
        print(f"turns   : {len(result.turns)} events")
        if args.plot:
            print(f"plot    : {viz.plot(result, args.plot)}")
        if args.overlay:
            print(f"overlay : {viz.overlay(args.video, result, args.overlay, cfg)}")
