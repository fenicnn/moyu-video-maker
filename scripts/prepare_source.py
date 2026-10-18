#!/usr/bin/env python3
"""Stage a local video or a public video URL and inventory subtitle sources.

This helper deliberately performs only deterministic media operations. It never
starts or calls a local language/speech model. Cloud transcription and semantic
translation remain agent steps governed by SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path


VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".webm", ".m4v"}
SUBTITLE_SUFFIXES = {".srt", ".ass", ".ssa", ".vtt"}
TEXT_SUBTITLE_CODECS = {"subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text"}


def run(command: list[str], dry_run: bool = False) -> int:
    print(" $", " ".join(command))
    if dry_run:
        return 0
    return subprocess.run(command, check=False).returncode


def opensubtitles_hash(path: Path) -> str:
    """Return the OpenSubtitles OSHash for a video file."""
    size = path.stat().st_size
    if size < 131_072:
        raise ValueError("OpenSubtitles hash requires a file of at least 128 KiB")
    checksum = size
    with path.open("rb") as handle:
        for offset in (0, size - 65_536):
            handle.seek(offset)
            chunk = handle.read(65_536)
            checksum += sum(struct.unpack("<8192Q", chunk))
    return f"{checksum & 0xFFFFFFFFFFFFFFFF:016x}"


def ytdlp_command(url: str, source_dir: Path, stem: str) -> list[str]:
    output = str(source_dir / f"{stem}.%(ext)s")
    return [
        "yt-dlp", "--no-playlist",
        "-f", "bv*[height<=1080]+ba/b[height<=1080]",
        "--merge-output-format", "mp4", "--remux-video", "mp4",
        "--write-subs", "--write-auto-subs",
        "--sub-langs", "en.*,zh.*,zh-Hans,zh-Hant",
        "--sub-format", "srt/best", "--convert-subs", "srt",
        "--write-info-json", "--no-write-playlist-metafiles",
        "-o", output, url,
    ]


def probe_subtitle_streams(video: Path) -> list[dict]:
    if shutil.which("ffprobe") is None:
        return []
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "s",
            "-show_entries", "stream=index,codec_name:stream_tags=language,title",
            "-of", "json", str(video),
        ],
        check=False, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout).get("streams", [])
    except json.JSONDecodeError:
        return []


def extract_text_subtitles(video: Path, subtitle_dir: Path, dry_run: bool = False) -> list[dict]:
    streams = probe_subtitle_streams(video)
    extracted: list[dict] = []
    if not streams or shutil.which("ffmpeg") is None:
        return extracted
    subtitle_dir.mkdir(parents=True, exist_ok=True)
    for stream in streams:
        codec = str(stream.get("codec_name", "")).casefold()
        tags = stream.get("tags") or {}
        language = re.sub(r"[^A-Za-z0-9_-]+", "-", str(tags.get("language") or "und"))
        record = {
            "index": stream.get("index"),
            "codec": codec,
            "language": language,
            "title": tags.get("title", ""),
            "status": "bitmap-or-unsupported",
        }
        if codec in TEXT_SUBTITLE_CODECS:
            output = subtitle_dir / f"embedded-{stream['index']}-{language}.srt"
            rc = run([
                "ffmpeg", "-y", "-v", "error", "-i", str(video),
                "-map", f"0:{stream['index']}", "-c:s", "srt", str(output),
            ], dry_run=dry_run)
            record["status"] = "extracted" if rc == 0 else "extract-failed"
            record["path"] = str(output)
        extracted.append(record)
    return extracted


def subtitle_characteristics(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return {
        "path": str(path),
        "latin": len(re.findall(r"[A-Za-z]", text)),
        "cjk": len(re.findall(r"[\u3400-\u9fff]", text)),
        "timings": text.count(" --> "),
    }


def sidecar_subtitles(video: Path) -> list[dict]:
    candidates = []
    for path in sorted(video.parent.iterdir()):
        if path.is_file() and path.suffix.casefold() in SUBTITLE_SUFFIXES:
            candidates.append(subtitle_characteristics(path))
    return candidates


def opensubtitles_search(video: Path, title: str | None) -> dict:
    api_key = os.environ.get("OPENSUBTITLES_API_KEY")
    if not api_key:
        return {"status": "skipped", "reason": "OPENSUBTITLES_API_KEY is not set"}
    params = {
        "languages": "en,zh-cn,zh-tw",
        "moviehash": opensubtitles_hash(video),
    }
    if title:
        params["query"] = title
    url = "https://api.opensubtitles.com/api/v1/subtitles?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={
            "Api-Key": api_key,
            "User-Agent": "moyu-video-maker v3.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        return {"status": "ok", "query": url, "data": payload.get("data", [])}
    except Exception as error:  # network/provider errors are recorded, not hidden
        return {"status": "error", "query": url, "error": str(error)}


def locate_downloaded_video(source_dir: Path, stem: str) -> Path | None:
    matches = [
        path for path in source_dir.glob(f"{stem}.*")
        if path.is_file() and path.suffix.casefold() in VIDEO_SUFFIXES
    ]
    return matches[0] if len(matches) == 1 else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage a local video or public URL and inventory reusable subtitles"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="Public video URL supported by yt-dlp")
    source.add_argument("--video", type=Path, help="Existing local video")
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--stem", default="source", help="Stable working filename stem")
    parser.add_argument("--title", help="Optional title for provider search")
    parser.add_argument(
        "--network-policy", choices=["offline", "allow"], default="offline",
        help="Network access must be explicitly allowed by the caller",
    )
    parser.add_argument("--search-opensubtitles", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not re.fullmatch(r"[^/\\]+", args.stem) or args.stem in {".", ".."}:
        print("[prepare-source] --stem must be a single safe filename component", file=sys.stderr)
        return 2

    args.work_dir.mkdir(parents=True, exist_ok=True)
    source_dir = args.work_dir / "source"
    subtitle_dir = args.work_dir / "subtitles"
    source_dir.mkdir(parents=True, exist_ok=True)
    subtitle_dir.mkdir(parents=True, exist_ok=True)

    video: Path | None
    if args.url:
        if args.network_policy != "allow":
            print("[prepare-source] URL input requires --network-policy allow", file=sys.stderr)
            return 2
        if shutil.which("yt-dlp") is None:
            print("[prepare-source] yt-dlp is not installed", file=sys.stderr)
            return 2
        rc = run(ytdlp_command(args.url, source_dir, args.stem), dry_run=args.dry_run)
        if rc != 0:
            return rc
        if args.dry_run:
            return 0
        video = locate_downloaded_video(source_dir, args.stem)
        if video is None:
            print("[prepare-source] expected exactly one downloaded video", file=sys.stderr)
            return 2
    else:
        video = args.video
        if not video or not video.is_file():
            print(f"[prepare-source] video does not exist: {video}", file=sys.stderr)
            return 2

    embedded = extract_text_subtitles(video, subtitle_dir, dry_run=args.dry_run)
    sidecars = sidecar_subtitles(video)
    staged_subtitles = [
        subtitle_characteristics(path)
        for path in sorted(source_dir.glob(f"{args.stem}*.srt"))
    ]
    provider = {"status": "skipped", "reason": "not requested"}
    if args.search_opensubtitles:
        if args.network_policy != "allow":
            provider = {"status": "skipped", "reason": "network policy is offline"}
        else:
            provider = opensubtitles_search(video, args.title)

    manifest = {
        "schemaVersion": 1,
        "source": {"url": args.url, "video": str(video), "title": args.title},
        "video": {
            "path": str(video),
            "size": video.stat().st_size,
            "opensubtitlesHash": opensubtitles_hash(video) if video.stat().st_size >= 131_072 else None,
        },
        "subtitleSources": {
            "sidecar": sidecars,
            "downloaded": staged_subtitles,
            "embedded": embedded,
            "openSubtitles": provider,
        },
        "localModelUsed": False,
    }
    manifest_path = args.work_dir / "source-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[prepare-source] manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
