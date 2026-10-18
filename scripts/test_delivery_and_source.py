import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


PREPARE = load("prepare_source", "prepare_source.py")
PUBLISH = load("publish_deliverables", "publish_deliverables.py")


SRT = """1
00:00:01,000 --> 00:00:04,000
It is <font color="#ffd400">worth it</font>.
这是值得的。
"""

VOCAB = {
    "schemaVersion": 2,
    "vocabulary": [{
        "cueIndex": 1,
        "term": "worth it",
        "phonetic": "",
        "partOfSpeech": "phrase",
        "meaning": "值得",
    }],
}


class SourcePreparationTests(unittest.TestCase):
    def test_ytdlp_command_caps_resolution_and_requests_subtitles(self):
        command = PREPARE.ytdlp_command("https://example.test/video", Path("/tmp/work"), "source")
        joined = " ".join(command)
        self.assertIn("height<=1080", joined)
        self.assertIn("--write-subs", command)
        self.assertIn("--write-auto-subs", command)
        self.assertIn("--no-playlist", command)

    def test_opensubtitles_hash_matches_independent_calculation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "video.bin"
            data = bytes(range(256)) * 600
            path.write_bytes(data)
            expected = len(data)
            expected += sum(struct.unpack("<8192Q", data[:65536]))
            expected += sum(struct.unpack("<8192Q", data[-65536:]))
            expected &= 0xFFFFFFFFFFFFFFFF
            self.assertEqual(PREPARE.opensubtitles_hash(path), f"{expected:016x}")


class DeliveryTests(unittest.TestCase):
    def test_highlight_and_vocab_mapping_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            srt = root / "lesson.srt"
            vocab = root / "lesson.json"
            srt.write_text(SRT, encoding="utf-8")
            vocab.write_text(json.dumps(VOCAB), encoding="utf-8")
            self.assertEqual(PUBLISH.validate_srt_and_vocab(srt, vocab), [])

    def test_invalid_subtitles_are_rejected(self):
        cases = [
            SRT.replace("这是值得的。", ""),
            SRT.replace("00:00:04,000", "00:00:00,500"),
            SRT.replace("00:00:01,000", "00:60:01,000"),
            SRT + "\n2\ninvalid timing\nHello\n你好\n",
            SRT + "\n" + SRT,
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vocab = root / "lesson.json"
            vocab.write_text(json.dumps(VOCAB))
            for text in cases:
                with self.subTest(text=text):
                    srt = root / "lesson.srt"
                    srt.write_text(text)
                    self.assertTrue(PUBLISH.validate_srt_and_vocab(srt, vocab))

    def test_video_duration_bounds(self):
        self.assertEqual(PUBLISH.validate_timing(SRT, 4.0), [])
        self.assertTrue(PUBLISH.validate_timing(SRT, 3.9))

    def test_missing_ffprobe_blocks_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "lesson.mp4"
            video.write_bytes(b"placeholder")
            with patch.object(PUBLISH.shutil, "which", return_value=None):
                self.assertTrue(PUBLISH.validate_video(video))

    def test_old_vocabulary_format_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            srt, vocab = root / "lesson.srt", root / "lesson.json"
            srt.write_text(SRT)
            vocab.write_text(json.dumps({"schemaVersion": 1, "vocabulary": [
                {"id": "cue-1-000001000-term-0", "term": "worth it",
                 "phonetic": "", "partOfSpeech": "phrase", "meaning": "值得"}
            ]}))
            self.assertTrue(PUBLISH.validate_srt_and_vocab(srt, vocab))

    def test_mapping_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            srt = root / "lesson.srt"
            vocab = root / "lesson.json"
            srt.write_text(SRT, encoding="utf-8")
            payload = dict(VOCAB)
            payload["vocabulary"] = [dict(VOCAB["vocabulary"][0], term="wrong")]
            vocab.write_text(json.dumps(payload), encoding="utf-8")
            errors = PUBLISH.validate_srt_and_vocab(srt, vocab)
            self.assertTrue(any("does not exactly match" in error for error in errors))

    def test_directory_requires_exactly_three_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for suffix in (".mp4", ".srt", ".json"):
                (root / f"lesson{suffix}").write_bytes(b"x")
            with patch.object(PUBLISH, "validate_bundle", return_value=[]):
                self.assertEqual(PUBLISH.audit_directory(root, "lesson"), [])
                (root / "extra.txt").write_text("not allowed")
                self.assertTrue(PUBLISH.audit_directory(root, "lesson"))


if __name__ == "__main__":
    unittest.main()
