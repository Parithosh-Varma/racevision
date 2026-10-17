# racevision

Collect **driver-behavior data** from race stream URLs (GT4 / onboard POV cameras).

It records a stream, then derives driving proxies from the onboard video using
dense optical flow: a **speed signal**, **acceleration/braking points**, and a
**cornering / steering signal**. Outputs are CSV, a PNG plot, and an annotated
overlay video.

> These are *video-derived proxies*, not real telemetry. See [Limitations](#limitations).

## Install

Requires **Python 3.10+** (3.12 recommended). Live YouTube capture also needs
[Deno](https://deno.land) and a current yt-dlp.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[plot]"       # [plot] adds matplotlib for --plot
pip install -U "yt-dlp[default]"
brew install deno            # macOS; or: curl -fsSL https://deno.land/install.sh | sh
```

`capture` is available as the `racevision` command or `python -m racevision`.
`ffmpeg` is required for stream muxing; if it is not on your PATH, the bundled
binary from `imageio-ffmpeg` is used automatically.

## Quick start

```bash
# 1. inspect a stream
racevision probe "https://www.youtube.com/watch?v=k3O8Zjp_1bw"

# 2. grab a live clip (see the 403 section below for the required flags)
racevision capture "https://www.youtube.com/watch?v=k3O8Zjp_1bw" -o pov.mp4 --seconds 120 \
  --cookies-from-browser brave --no-audio \
  --extractor-args "youtube:player_js_version=actual" \
  --ytdlp-arg=--js-runtimes --ytdlp-arg deno

# 3. analyze the onboard POV
racevision analyze pov.mp4 -o pov.csv --plot pov.png --overlay pov_overlay.mp4
```

## YouTube bot check

Datacenter / fresh IPs often get `Sign in to confirm you're not a bot`. Pass
your own browser cookies (do this on the machine where you are signed in):

```bash
racevision capture "<url>" -o pov.mp4 --seconds 120 --cookies-from-browser brave
# or export cookies to a file and use: --cookies cookies.txt
```

Use `--cookies-from-browser` with `chrome`, `firefox`, `edge`, `brave`, etc.

## Live stream `HTTP error 403 Forbidden`

YouTube requires a JS runtime (a "PO Token"/JS-challenge) for live streams, and
yt-dlp's fallbacks otherwise 403 on the `googlevideo` segments. **The working
recipe** is to install [Deno](https://deno.land) and pass the JS runtime:

```bash
brew install deno   # or: curl -fsSL https://deno.land/install.sh | sh

racevision capture "<url>" -o pov.mp4 --seconds 120 \
  --cookies-from-browser brave --no-audio \
  --extractor-args "youtube:player_js_version=actual" \
  --ytdlp-arg=--js-runtimes --ytdlp-arg deno
```

Also ensure you're on the latest yt-dlp (`pip install -U "yt-dlp[default]"`) and
Python 3.10+ (3.9 mishandles the TLS/JS challenge).

If it still 403s, try these in order:

```bash
# video-only: no audio muxing, so yt-dlp's native downloader fetches fragments
racevision capture "<url>" -o pov.mp4 --seconds 120 --cookies-from-browser brave --no-audio

# force IPv4 (signed URLs are IP-bound; IPv4/IPv6 mismatch can cause 403)
racevision capture "<url>" -o pov.mp4 --seconds 120 --cookies-from-browser brave --no-audio -4

# pin the extracting client
racevision capture "<url>" -o pov.mp4 --seconds 120 --cookies-from-browser brave --no-audio \
    --extractor-args "youtube:player_client=tv"
```

`--ytdlp-arg` passes any raw flag to yt-dlp; use `--ytdlp-arg=--flag` (with `=`)
when the value itself starts with a dash. Run capture with `--no-audio` for
analysis — the tool only reads video frames.

## Commands

| Command   | Purpose                                                     |
|-----------|-------------------------------------------------------------|
| `probe`   | Print stream metadata as JSON (id, live, duration, res)     |
| `capture` | Download/record a stream to a local video                   |
| `analyze` | Run driver-behavior analysis on a POV video                 |

### `analyze` options

| Flag             | Default | Meaning                                              |
|------------------|---------|------------------------------------------------------|
| `--sample-fps`   | 10      | frames per second to process                         |
| `--width`        | 480     | resize width before flow (speed vs. accuracy)        |
| `--top-cut`      | 0.15    | fraction of top cropped (sky / broadcast HUD)        |
| `--bottom-cut`   | 0.12    | fraction of bottom cropped (dash / car hood)         |
| `--plot`         | -       | write PNG plot                                       |
| `--overlay`      | -       | write annotated MP4                                  |

Tune the crops so the analysis region covers road/cockpit view and excludes
static HUD graphics — static overlays distort the flow estimates.

## Outputs

- `<video>.csv` — per-sample `t, speed, accel, lateral, expansion, braking, turn_dir`
- `<video>.events.csv` — detected `brake` / `turn` events with start, end, duration, peak
- optional PNG plot and annotated overlay video

## How it works

1. Frames are sampled and downscaled to grayscale.
2. A region of interest excludes HUD/sky; the focus of expansion sits at ROI center.
3. Dense optical flow (Farneback) gives per-sample features:
   - `speed` — median flow magnitude (forward motion ≈ speed)
   - `lateral` — signed median horizontal flow (cornering: world flows opposite to car yaw)
   - `expansion` — radial flow relative to the focus of expansion
4. Features are smoothed; `accel` is the time derivative of `speed`.
5. Values below the `brake_pct` percentile of `accel` are braking; large `|lateral|`
   values are cornering. Short blips are dropped (`--sample-fps`-scaled `min_event_sec`).

## Limitations

- No absolute speed/GPS without an on-screen telemetry or GPS overlay; values are
  *relative proxies* and only comparable within one clip/camera setup.
- Camera stabilization and swapped/different onboard angles change the flow scale.
- Braking detection reflects *deceleration*, which includes engine braking and
  off-throttle, not only brake-pedal application.
- `lateral` gives a cornering *direction/magnitude proxy*, not steering angle.

## Development

Generate a synthetic clip and run the pipeline without any network access:

```bash
python tools/make_sample.py /tmp/sample.mp4
python -m racevision analyze /tmp/sample.mp4 --plot /tmp/sample.png
```
