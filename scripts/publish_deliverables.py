#!/usr/bin/env python3
"""Publish and audit the strict three-file Moyu deliverable directory."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from moyu_pipeline import parse_highlighted_srt


def validate_video(path: Path) -> list[str]:
    errors: list[str] = []
    if path.suffix.casefold() != ".mp4":
        errors.append("video must use the .mp4 extension")
    if not path.is_file() or path.stat().st_size == 0:
        errors.append("video is missing or empty")
        return errors
    if not shutil.which("ffprobe"):
        return errors + ["ffprobe is required; install FFmpeg before publishing"]
    if shutil.which("ffprobe"):
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(path)],
            check=False, capture_output=True, text=True,
        )
        try:
            streams = json.loads(result.stdout).get("streams", []) if result.returncode == 0 else []
        except json.JSONDecodeError:
            streams = []
        kinds = {stream.get("codec_type") for stream in streams}
        if "video" not in kinds or "audio" not in kinds:
            errors.append("MP4 must contain decodable video and audio streams")
    return errors


def video_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    duration = float(json.loads(result.stdout)["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("invalid video duration")
    return duration


def validate_timing(text: str, duration: float | None) -> list[str]:
    errors = []
    previous_index, previous_start = 0, -1.0
    normalized = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    pattern = re.compile(r"(\d{2,}):([0-5]\d):([0-5]\d),(\d{3}) --> (\d{2,}):([0-5]\d):([0-5]\d),(\d{3})")
    for number, block in enumerate(re.split(r"\n\s*\n", normalized), 1):
        lines = block.splitlines()
        timing = pattern.fullmatch(lines[1].strip()) if len(lines) >= 3 else None
        if not lines or not lines[0].strip().isdigit() or not timing:
            errors.append(f"SRT block {number}: invalid index, timing or missing content")
            continue
        index = int(lines[0].strip())
        values = list(map(int, timing.groups()))
        start = values[0]*3600 + values[1]*60 + values[2] + values[3]/1000
        end = values[4]*3600 + values[5]*60 + values[6] + values[7]/1000
        if index <= previous_index or start < previous_start or end <= start:
            errors.append(f"SRT cue {index}: indices/start times must increase and end must follow start")
        if duration is not None and end > duration + 0.001:
            errors.append(f"SRT cue {index}: ends beyond video duration")
        previous_index, previous_start = index, start
    return errors


def validate_srt_and_vocab(srt: Path, vocab_path: Path, duration: float | None = None) -> list[str]:
    errors: list[str] = []
    try:
        text = srt.read_text(encoding="utf-8-sig")
    except OSError as error:
        return [f"cannot read SRT: {error}"]
    errors.extend(validate_timing(text, duration))
    cues = parse_highlighted_srt(text)
    if not cues:
        errors.append("SRT contains no valid cues")
    for cue in cues:
        if not cue["english"] or not cue["chinese"]:
            errors.append(f"SRT cue {cue['cueIndex']}: requires both English and Chinese")
    tagged = [
        (cue["cueIndex"], term["term"])
        for cue in cues for term in cue["terms"]
    ]
    if not tagged:
        errors.append("SRT contains no highlighted vocabulary")
    if text.lower().count("<font") != text.lower().count("</font>"):
        errors.append("SRT has unbalanced font tags")
    if text.lower().count("<span") != text.lower().count("</span>"):
        errors.append("SRT has unbalanced span tags")

    try:
        payload = json.loads(vocab_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        return errors + [f"invalid vocabulary JSON: {error}"]
    if not isinstance(payload, dict):
        return errors + ["vocabulary JSON must be an object"]
    vocabulary = payload.get("vocabulary")
    if payload.get("schemaVersion") != 2 or not isinstance(vocabulary, list):
        errors.append("vocabulary JSON must use schemaVersion 2")
        return errors
    required = {"cueIndex", "term", "phonetic", "partOfSpeech", "meaning"}
    if any(not isinstance(item, dict) or not required.issubset(item) for item in vocabulary):
        errors.append("vocabulary JSON contains an invalid entry")
        return errors
    mapped = [(item["cueIndex"], item["term"]) for item in vocabulary]
    if mapped != tagged:
        errors.append("JSON cueIndex/term sequence does not exactly match highlighted SRT")
    for item in vocabulary:
        if type(item["cueIndex"]) is not int:
            errors.append("cueIndex must be an integer")
            break
        if not all(isinstance(item[key], str) for key in ("term", "phonetic", "partOfSpeech", "meaning")):
            errors.append("vocabulary text fields must be strings")
            break
        if not item["term"].strip() or not item["partOfSpeech"].strip() or not item["meaning"].strip():
            errors.append("term, partOfSpeech and meaning must be non-empty")
            break
    return errors


def validate_bundle(video: Path, srt: Path, vocab: Path) -> list[str]:
    errors = validate_video(video)
    if errors:
        return errors
    try:
        duration = video_duration(video)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
        return [f"cannot validate video duration: {error}"]
    return validate_srt_and_vocab(srt, vocab, duration)


def expected_names(stem: str) -> set[str]:
    return {f"{stem}.mp4", f"{stem}.srt", f"{stem}.json"}


def audit_directory(directory: Path, stem: str) -> list[str]:
    if not directory.is_dir():
        return ["deliverable directory does not exist"]
    entries = {path.name for path in directory.iterdir()}
    expected = expected_names(stem)
    errors = []
    if entries != expected:
        errors.append(f"directory must contain exactly {sorted(expected)}; found {sorted(entries)}")
        return errors
    errors.extend(validate_bundle(directory / f"{stem}.mp4", directory / f"{stem}.srt", directory / f"{stem}.json"))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish exactly MP4 + highlighted SRT + vocabulary JSON")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--srt", type=Path, required=True)
    parser.add_argument("--vocab", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--stem", required=True)
    parser.add_argument("--force", action="store_true", help="replace only the three expected files")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not re.fullmatch(r"[^/\\]+", args.stem) or args.stem in {".", ".."}:
        print("[publish] --stem must be a single safe filename component", file=sys.stderr)
        return 2
    inputs = [args.video, args.srt, args.vocab]
    if any(not path.is_file() for path in inputs):
        print("[publish] every input must be an existing file", file=sys.stderr)
        return 2
    errors = validate_bundle(args.video, args.srt, args.vocab)
    if errors:
        for error in errors:
            print(f"[publish] INVALID: {error}", file=sys.stderr)
        return 2

    expected = expected_names(args.stem)
    if args.output_dir.exists():
        existing = {path.name for path in args.output_dir.iterdir()}
        if existing and (existing != expected or not args.force):
            print(
                "[publish] output exists; use a fresh directory, or --force only when it already contains exactly the expected three files",
                file=sys.stderr,
            )
            return 2
    if args.dry_run:
        print(f"[publish] would publish {sorted(expected)} to {args.output_dir}")
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    pairs = [
        (args.video, args.output_dir / f"{args.stem}.mp4"),
        (args.srt, args.output_dir / f"{args.stem}.srt"),
        (args.vocab, args.output_dir / f"{args.stem}.json"),
    ]
    temporaries: list[Path] = []
    try:
        for source, target in pairs:
            temporary = target.with_name(f".{target.name}.moyu-part-{os.getpid()}")
            shutil.copy2(source, temporary)
            temporaries.append(temporary)
        for temporary, (_, target) in zip(temporaries, pairs):
            os.replace(temporary, target)
    finally:
        for temporary in temporaries:
            if temporary.exists():
                temporary.unlink()
    errors = audit_directory(args.output_dir, args.stem)
    if errors:
        for error in errors:
            print(f"[publish] INVALID AFTER PUBLISH: {error}", file=sys.stderr)
        return 2
    print(f"[publish] complete: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
