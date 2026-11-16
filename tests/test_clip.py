import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from autopost import clip


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def dims(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "json", str(path)],
                         check=True, capture_output=True).stdout
    s = json.loads(out)["streams"][0]
    return s["width"], s["height"]


class ClipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        # 60 sn, 16:9; ses yalnızca 30-50. saniyeler arasında yüksek
        cls.video = cls.tmp / "src.mp4"
        ff("-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=60",
           "-f", "lavfi", "-i", "sine=f=440:d=60",
           "-af", "volume='if(between(t,30,50),1,0.05)':eval=frame",
           "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(cls.video))
        cls.audio = cls.tmp / "src.wav"
        ff("-i", str(cls.video), "-vn", str(cls.audio))

    def test_best_window_finds_loud_part(self):
        start, length = clip.best_window(clip.energy_per_second(self.video), 15)
        self.assertEqual(length, 15)
        self.assertTrue(30 <= start <= 35, start)

    def test_exclude_moves_window(self):
        e = clip.energy_per_second(self.video)
        s1, _ = clip.best_window(e, 15)
        s2, _ = clip.best_window(e, 15, exclude=[(s1, s1 + 15)])
        self.assertTrue(s2 + 15 <= s1 or s2 >= s1 + 15)

    def test_video_source_gives_vertical_clip(self):
        out = clip.make_clip(self.video, self.tmp / "o1.mp4", 31, 10)
        self.assertEqual(dims(out), (1080, 1920))
        dur, has_v, has_a = clip.probe(out)
        self.assertTrue(has_v and has_a)
        self.assertAlmostEqual(dur, 10, delta=0.6)

    def test_audio_only_source_gives_vertical_clip(self):
        out = clip.make_clip(self.audio, self.tmp / "o2.mp4", 31, 8)
        self.assertEqual(dims(out), (1080, 1920))
        self.assertAlmostEqual(clip.probe(out)[0], 8, delta=0.6)


if __name__ == "__main__":
    unittest.main()
