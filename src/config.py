import json
import os

import numpy as np
import soundfile as sf

from src.util import CONFIG_PATH, MODES, PROJECT_ROOT

# Fixed DewesoftX channel names.
MASTER_CHANNEL = "Master"
SLIDER_CHANNEL = "Slider"

# Song sample files read by the C++ Scripts.
SONG_DIR = os.path.join(PROJECT_ROOT, "song_files")
SONG_FILES = (os.path.join(SONG_DIR, "first_song.txt"), os.path.join(SONG_DIR, "second_song.txt"))


class Config:
    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self.mode = None
        self.master_channel = None
        self.slider_channel = None
        self.first_song = None
        self.second_song = None

    def read(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except OSError as e:
            raise RuntimeError("Cannot read %s (%s). Run write_config.py first." % (self.path, e))
        except json.JSONDecodeError as e:
            raise RuntimeError("%s is not valid JSON (%s)." % (self.path, e))

        try:
            self.mode = data["mode"]
            self.master_channel = data["master_channel"]
            self.slider_channel = data["slider_channel"]
            self.first_song = data["first_song"]
            self.second_song = data["second_song"]
        except KeyError as e:
            raise RuntimeError("%s is missing the key %s. Run write_config.py again." % (self.path, e))

        if self.mode not in MODES:
            raise RuntimeError("%s: mode %r must be one of: %s" % (self.path, self.mode, ", ".join(MODES)))
        return self

    def update(self, mode, first_song_path=None, second_song_path=None):
        if mode not in MODES:
            raise RuntimeError("Application mode must be one of: %s" % ", ".join(MODES))

        paths = []
        for path in (first_song_path, second_song_path):
            if path is not None:
                path = os.path.abspath(path)
                if not os.path.isfile(path):
                    raise RuntimeError("File not found: %s" % path)
            paths.append(path)

        rates = [None, None]
        if mode == "music_mix":
            if None in paths:
                raise RuntimeError("music_mix needs both songs.")
            for i, (src, dst) in enumerate(zip(paths, SONG_FILES)):
                try:
                    rates[i] = _save_song_samples(src, dst)
                except (OSError, RuntimeError) as e:  # soundfile raises LibsndfileError (RuntimeError)
                    raise RuntimeError("Could not convert %s: %s" % (src, e))

        self.mode = mode
        self.master_channel = MASTER_CHANNEL
        self.slider_channel = SLIDER_CHANNEL
        self.first_song = {"path": paths[0], "sample_rate": rates[0]}
        self.second_song = {"path": paths[1], "sample_rate": rates[1]}
        return self

    def write(self):
        state = {
            "mode": self.mode,
            "master_channel": self.master_channel,
            "slider_channel": self.slider_channel,
            "first_song": self.first_song,
            "second_song": self.second_song,
        }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=4)
            os.replace(tmp, self.path)
        except OSError as e:
            raise RuntimeError("Could not write %s: %s" % (self.path, e))


def _save_song_samples(src, dst):
    samples, rate = sf.read(src, dtype="float32", always_2d=True)
    mono = samples.mean(axis=1)  # Stereo to mono.

    # Write to a temp file first so the C++ Script never reads a half-written file.
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".tmp"
    np.savetxt(tmp, mono, fmt="%.7g")
    os.replace(tmp, dst)
    return rate
