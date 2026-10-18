#!/usr/bin/env python3
"""Read-only, task-aware dependency checks. Never installs software or calls AI."""
import argparse
import shutil
import subprocess
import sys


def check_tool(name):
    executable = shutil.which(name)
    if not executable:
        return False
    try:
        result = subprocess.run(
            [executable, '--version' if name == 'yt-dlp' else '-version'],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', choices=['local', 'url', 'srt'], default='local',
                        help='url also requires yt-dlp; every route requires FFmpeg for delivery')
    args = parser.parse_args(argv)
    missing = sys.version_info < (3, 10)
    print(('MISSING' if missing else 'OK') + ': Python 3.10+ (scripts)')
    required = ['ffmpeg', 'ffprobe'] + (['yt-dlp'] if args.source == 'url' else [])
    for tool in required:
        ok = check_tool(tool)
        missing |= not ok
        purpose = 'link download' if tool == 'yt-dlp' else 'media processing and delivery validation'
        hint = 'install yt-dlp' if tool == 'yt-dlp' else 'install FFmpeg (includes ffprobe)'
        print(f"{'OK' if ok else 'MISSING'}: {tool} ({purpose})" + (f'; {hint}' if not ok else ''))
    print('INFO: AI selection/translation requires an authorized cloud AI; this check does not call or verify a provider.')
    return 1 if missing else 0


if __name__ == '__main__':
    raise SystemExit(main())
