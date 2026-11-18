import json
import os

import numpy as np
import soundfile as sf
from bpm_finder import analyze_audio_file

from src.utils.util import CONFIG_PATH, PROJECT_ROOT

# Fixed DewesoftX channel names.
MASTER_CHANNEL = "Master"
MIXER_SLIDER_CHANNEL = "Mixer_slider"
VOLUME_SLIDER_CHANNEL = "Volume_slider"
DRUM_SELECTION_CHANNEL = "Drum_selection"
DRUM_CHANNEL = "Drum trigger"
ENCODER_MODE_CHANNEL = "Encoder_mode"
ENCODER_CHANNEL = "Encoder output"
TUNING_FORK_CHANNEL = "Tuning fork sound"

# Song sample files read by the C++ Scripts.
SONG_DIR = os.path.join(PROJECT_ROOT, "song_files")
SONG_FILES = (os.path.join(SONG_DIR, "first_song.bin"), os.path.join(SONG_DIR, "second_song.bin"))

# Song tempo detection (bpm_finder).
BPM_MIN = 70.0
BPM_MAX = 180.0


class Config:
    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self.master_channel = None
        self.mixer_slider_channel = None
        self.volume_slider_channel = None
        self.drum_selection_channel = None
        self.drum_channel = None
        self.encoder_mode_channel = None
        self.encoder_channel = None
        self.tuning_fork_channel = None
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
            self.master_channel = data["master_channel"]
            self.mixer_slider_channel = data["mixer_slider_channel"]
            self.volume_slider_channel = data["volume_slider_channel"]
            self.drum_selection_channel = data["drum_selection_channel"]
            self.drum_channel = data["drum_channel"]
            self.encoder_mode_channel = data["encoder_mode_channel"]
            self.encoder_channel = data["encoder_channel"]
            self.tuning_fork_channel = data["tuning_fork_channel"]
            self.first_song = data["first_song"]
            self.second_song = data["second_song"]
        except KeyError as e:
            raise RuntimeError("%s is missing the key %s. Run write_config.py again." % (self.path, e))

        return self

    def update(self, first_song_path, second_song_path):
        paths = []
        for path in (first_song_path, second_song_path):
            if not path:
                raise RuntimeError("Both songs are required.")
            path = os.path.abspath(path)
            if not os.path.isfile(path):
                raise RuntimeError("File not found: %s" % path)
            paths.append(path)

        rates = [None, None]
        bpms = [None, None]
        for i, (src, dst) in enumerate(zip(paths, SONG_FILES)):
            try:
                rates[i], bpms[i] = _save_song_samples(src, dst)
            except (OSError, RuntimeError) as e:  # soundfile raises LibsndfileError (RuntimeError)
                raise RuntimeError("Could not convert %s: %s" % (src, e))

        self.master_channel = MASTER_CHANNEL
        self.mixer_slider_channel = MIXER_SLIDER_CHANNEL
        self.volume_slider_channel = VOLUME_SLIDER_CHANNEL
        self.drum_selection_channel = DRUM_SELECTION_CHANNEL
        self.drum_channel = DRUM_CHANNEL
        self.encoder_mode_channel = ENCODER_MODE_CHANNEL
        self.encoder_channel = ENCODER_CHANNEL
        self.tuning_fork_channel = TUNING_FORK_CHANNEL
        self.first_song = {"path": paths[0], "sample_rate": rates[0], "bpm": bpms[0]}
        self.second_song = {"path": paths[1], "sample_rate": rates[1], "bpm": bpms[1]}
        return self

    def write(self):
        state = {
            "master_channel": self.master_channel,
            "mixer_slider_channel": self.mixer_slider_channel,
            "volume_slider_channel": self.volume_slider_channel,
            "drum_selection_channel": self.drum_selection_channel,
            "drum_channel": self.drum_channel,
            "encoder_mode_channel": self.encoder_mode_channel,
            "encoder_channel": self.encoder_channel,
            "tuning_fork_channel": self.tuning_fork_channel,
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

    # Raw float32 samples (binary, no text formatting).
    mono.astype(np.float32).tofile(tmp)
    os.replace(tmp, dst)

    return rate, _detect_bpm(mono, rate, dst + ".wav")


def _detect_bpm(mono, rate, wav_path):
    sf.write(wav_path, mono, rate, subtype="PCM_16")
    try:
        return analyze_audio_file(wav_path, min_bpm=BPM_MIN, max_bpm=BPM_MAX)
    except ValueError as e:
        raise RuntimeError("BPM detection failed: %s" % e)
    finally:
        os.remove(wav_path)

