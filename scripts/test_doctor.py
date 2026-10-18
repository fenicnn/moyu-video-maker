import contextlib
import io
import unittest
from unittest.mock import patch

import doctor


class DoctorTests(unittest.TestCase):
    def test_local_does_not_require_downloader(self):
        with patch.object(doctor, 'check_tool', return_value=True) as check, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(doctor.main(['--source', 'local']), 0)
            self.assertEqual([call.args[0] for call in check.call_args_list], ['ffmpeg', 'ffprobe'])

    def test_url_fails_when_downloader_missing(self):
        with patch.object(doctor, 'check_tool', side_effect=lambda tool: tool != 'yt-dlp'), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(doctor.main(['--source', 'url']), 1)

    def test_probe_missing_blocks_every_route(self):
        for source in ['local', 'url', 'srt']:
            with self.subTest(source=source), patch.object(doctor, 'check_tool', side_effect=lambda tool: tool != 'ffprobe'), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(doctor.main(['--source', source]), 1)
