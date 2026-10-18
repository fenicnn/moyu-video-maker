import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


SCRIPT = Path(__file__).with_name("moyu_pipeline.py")
SPEC = importlib.util.spec_from_file_location("moyu_pipeline", SCRIPT)
PIPELINE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(PIPELINE)


SAMPLE = """1
00:00:01,000 --> 00:00:04,000
This is <font color="yellow">figure out</font>, <span style="font-weight:bold; color: rgb(99, 102, 241)">worth it</span> and <font color="#fff">RUN</font>.
这是<font color="#ff0">弄清楚</font>，英文重复写作 <font color="#0ff">run</font>。
"""


class PipelineTests(unittest.TestCase):
    def test_highlight_extraction_matches_studio_rules(self):
        cues = PIPELINE.parse_highlighted_srt(SAMPLE)
        self.assertEqual(
            cues[0]["terms"],
            [
                {"term": "figure out", "color": "yellow"},
                {"term": "worth it", "color": "rgb(99, 102, 241)"},
                {"term": "RUN", "color": "#fff"},
            ],
        )

    def test_builds_released_client_v1_ids_and_optional_v2(self):
        cues = PIPELINE.parse_highlighted_srt(SAMPLE)
        v1, _ = PIPELINE.build_vocabulary_payload(cues, 1)
        v2, _ = PIPELINE.build_vocabulary_payload(cues, 2)
        self.assertEqual(v1["vocabulary"][0]["id"], "cue-1-000001000-term-0")
        self.assertNotIn("cueIndex", v1["vocabulary"][0])
        self.assertEqual(v2["vocabulary"][0]["cueIndex"], 1)
        self.assertNotIn("id", v2["vocabulary"][0])

    def test_vocab_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.srt"
            output = root / "result.json"
            source.write_text(SAMPLE, encoding="utf-8")
            result = PIPELINE.cmd_vocab(Namespace(
                output=str(output), hl_srt=str(source), prompt_md=None,
                schema=1, prompt_output=None, no_prompt=False,
                force=False, dry_run=True,
            ))
            self.assertEqual(result, 0)
            self.assertFalse(output.exists())

    def test_cli_defaults_to_schema_version_2(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.srt"
            output = root / "result.json"
            source.write_text(SAMPLE, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "vocab", "--hl-srt", str(source), "--output", str(output)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text())["schemaVersion"], 2)

    def test_apply_selection_writes_expected_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            work.mkdir()
            (work / "srt.original.txt").write_text(SAMPLE, encoding="utf-8")
            source = root / "selection.json"
            source.write_text(json.dumps({"words": {"1": ["worth it", "worth it"]}, "corrections": {}}), encoding="utf-8")
            result = PIPELINE.cmd_apply_selection(Namespace(
                input=str(source), work_dir=str(work), episode="e01",
                force=False, dry_run=False,
            ))
            self.assertEqual(result, 0)
            self.assertEqual(json.loads((root / "work/e01_words.json").read_text()), {"1": ["worth it"]})

    def test_apply_selection_deduplicates_only_within_cue_and_repeats_later(self):
        repeated = """1
00:00:01,000 --> 00:00:04,000
It is worth it, really worth it.
这很值得，真的值得。

2
00:00:05,000 --> 00:00:08,000
Worth it again.
再次值得。

3
00:00:09,000 --> 00:00:12,000
Still worth it.
依然值得。
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            work.mkdir()
            (work / "srt.original.txt").write_text(repeated, encoding="utf-8")
            source = root / "selection.json"
            source.write_text(json.dumps({"words": {"1": ["worth it"]}, "corrections": {}}), encoding="utf-8")
            result = PIPELINE.cmd_apply_selection(Namespace(
                input=str(source), work_dir=str(work), episode="e01",
                force=False, dry_run=False,
            ))
            self.assertEqual(result, 0)
            self.assertEqual(
                json.loads((work / "e01_words.json").read_text()),
                {"1": ["worth it"], "2": ["Worth it"], "3": ["worth it"]},
            )

    def test_highlight_parser_keeps_same_term_in_different_cues(self):
        repeated = """1
00:00:01,000 --> 00:00:04,000
<font color=\"yellow\">worth it</font>, really <font color=\"yellow\">worth it</font>.
值得，真的值得。

2
00:00:05,000 --> 00:00:08,000
Still <font color=\"yellow\">worth it</font>.
依然值得。
"""
        self.assertEqual(
            PIPELINE.extract_terms_from_hl_srt(repeated),
            [{"cueIndex": 1, "term": "worth it"}, {"cueIndex": 2, "term": "worth it"}],
        )

    def test_empty_finish_fails(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "finish"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--srt 必填", result.stderr)

    def test_mp4_is_reused_unless_transcode_is_explicit(self):
        self.assertFalse(PIPELINE.should_transcode_video("episode.mp4"))
        self.assertFalse(PIPELINE.should_transcode_video("EPISODE.MP4"))
        self.assertTrue(PIPELINE.should_transcode_video("episode.mkv"))
        self.assertTrue(PIPELINE.should_transcode_video("episode.mp4", transcode_mp4=True))

    def test_selection_prompt_carries_confirmed_learning_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = PIPELINE.build_selection_prompt(
                root, "e01", SAMPLE, root, learning_profile="雅思7分"
            )
            text = prompt.read_text(encoding="utf-8")
            self.assertIn("学习范围：雅思7分", text)
            self.assertIn("筛选原则：重要程度优先，不按频率或数量筛选", text)
            self.assertIn("禁止数量驱动", text)
            self.assertIn("去重范围仅限同一 cue", text)
            self.assertIn("后续出现必须继续显示", text)
            self.assertNotIn("筛选密度：", text)
            self.assertNotIn("精简约每分钟", text)

    def test_end_to_end_defaults_to_v2(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Show.S02E04.srt"
            source.write_text("""1
00:00:01,000 --> 00:00:04,000
It is worth it.
这是值得的。
""", encoding="utf-8")
            init = subprocess.run(
                [sys.executable, str(SCRIPT), "init", "--srt", str(source), "--episode", "e04"],
                capture_output=True, text=True,
            )
            self.assertEqual(init.returncode, 0, init.stderr)
            work = root / ".moyu-work/e04"
            profile = json.loads((work / "learning-profile.json").read_text())
            self.assertEqual(profile["selectionPolicy"], "importance-first")
            self.assertNotIn("density", profile)
            selection = root / "selection.json"
            selection.write_text(json.dumps({"words": {"1": ["worth it"]}, "corrections": {}}), encoding="utf-8")
            apply = subprocess.run(
                [sys.executable, str(SCRIPT), "apply-selection", "--input", str(selection),
                 "--episode", "e04", "--work-dir", str(work)],
                capture_output=True, text=True,
            )
            self.assertEqual(apply.returncode, 0, apply.stderr)
            finish = subprocess.run(
                [sys.executable, str(SCRIPT), "finish", "--srt", str(source), "--episode", "e04"],
                capture_output=True, text=True,
            )
            self.assertEqual(finish.returncode, 0, finish.stderr)
            payload = json.loads((root / "moyu-ai-vocabulary.json").read_text())
            self.assertEqual(payload["schemaVersion"], 2)
            self.assertEqual(payload["vocabulary"][0]["cueIndex"], 1)
            self.assertTrue((root / "moyu-ai-vocabulary-prompt.md").exists())
            self.assertTrue((root / "Show.S02E04_高亮.srt").exists())


if __name__ == "__main__":
    unittest.main()
