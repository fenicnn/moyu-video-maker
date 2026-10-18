#!/usr/bin/env python3
"""Publish and audit the strict three-file Moyu deliverable directory."""

from __future__ import annotations

import argparse
import json
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


def validate_srt_and_vocab(srt: Path, vocab_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        text = srt.read_text(encoding="utf-8-sig")
    except OSError as error:
        return [f"cannot read SRT: {error}"]
    cues = parse_highlighted_srt(text)
    if not cues:
        errors.append("SRT contains no valid cues")
    if not any(cue["english"] and cue["chinese"] for cue in cues):
        errors.append("SRT is not bilingual English/Chinese")
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
        if not isinstance(item["cueIndex"], int):
            errors.append("cueIndex must be an integer")
            break
        if not all(isinstance(item[key], str) for key in ("term", "phonetic", "partOfSpeech", "meaning")):
            errors.append("vocabulary text fields must be strings")
            break
        if not item["term"].strip() or not item["partOfSpeech"].strip() or not item["meaning"].strip():
            errors.append("term, partOfSpeech and meaning must be non-empty")
            break
    return errors


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
    errors.extend(validate_video(directory / f"{stem}.mp4"))
    errors.extend(validate_srt_and_vocab(directory / f"{stem}.srt", directory / f"{stem}.json"))
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
    errors = validate_video(args.video) + validate_srt_and_vocab(args.srt, args.vocab)
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
