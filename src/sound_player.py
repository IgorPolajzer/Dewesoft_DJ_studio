import math
import os

import numpy as np
import sounddevice as sd
import soundfile as sf

from src.utils.util import PROJECT_ROOT

BLOCK_FRAMES = 256 # fixed callback block size (~5 ms at 48 kHz)

SLIDER_MIN = 0.0
SLIDER_MAX = 100.0

# Drum sounds.
DRUM_DIR = os.path.join(PROJECT_ROOT, "assets", "drums")
DRUM_STRENGTH_MAX = 10.0  # Drum hit strength 1-10.

# Note sounds.
NOTE_DIR = os.path.join(PROJECT_ROOT, "assets", "note")
NOTE_FILES = {1: "forward_note.wav", -1: "backwards_note.wav"}


def mix_gains(mixer, volume):
    """Song gains (gA, gB) from the raw slider values (0..100).

    x = mixer / 100  (0 = only the first song, 1 = only the second song)
    v = volume / 100 (0 = silent, 1 = full)
    gA = v² · cos(x·π/2),  gB = v² · sin(x·π/2)

    Equal-power crossfade: gA² + gB² = v⁴, so the loudness stays constant across the fade.
    v² makes the volume slider feel even along its travel. No headroom: around x = 0.5 the
    gain sum reaches 1.41, so loud passages of both songs together can clip.
    """
    x = min(max(mixer / SLIDER_MAX, 0.0), 1.0)
    v = min(max(volume / SLIDER_MAX, 0.0), 1.0)
    level = v * v
    return level * math.cos(x * math.pi / 2), level * math.sin(x * math.pi / 2)


def volume_gain(volume):
    """Gain v² from the raw volume slider value (0..100), as used for the songs."""
    v = min(max(volume / SLIDER_MAX, 0.0), 1.0)
    return v * v


class SoundPlayer:
    def __init__(self, first_song_path, second_song_path, first_gain, second_gain):
        device, rate, channels = _find_wasapi_output()
        self._device = device

        # Load both song files into RAM, resampled to the device rate).
        paths = (first_song_path, second_song_path)
        self.songs = [_load_audio(path, rate, channels) for path in paths] if None not in paths else []

        self.positions = [0.0, 0.0] # Positions of songs (fractional sample index).
        self.speeds = [1.0, 1.0] # Playback speed of each song (1 = original, 0 = stopped)
        self.gains = [float(first_gain), float(second_gain)] # the gain each song is playing at right now
        self.target_gains = [float(first_gain), float(second_gain)] # the gain each song should ramp to (set by set_gains)

        # Drum sounds.
        self.drums = [_load_audio(os.path.join(DRUM_DIR, f), rate, channels) for f in sorted(os.listdir(DRUM_DIR))]
        self._drum = None
        self._drum_pos = 0
        self._drum_gain = 0.0
        self._drum_request = None

        # Note sounds.
        self.notes = {k: _load_audio(os.path.join(NOTE_DIR, f), rate, channels) for k, f in NOTE_FILES.items()}
        self._note = None
        self._note_pos = 0
        self._note_request = None

        # Tuning fork: its own stream at the channel rate, opened by open_fork().
        self.fork_stream = None
        self._fork_gain = 1.0

        # Preallocated buffers for the callback.
        self._ramp = np.arange(1, BLOCK_FRAMES + 1, dtype=np.float32) / BLOCK_FRAMES # Ramp shape 1/256..1: fraction of the way from the old to the new gain, per sample.
        self._gain_buf = np.empty(BLOCK_FRAMES, dtype=np.float32)
        self._mix_buf = np.empty((BLOCK_FRAMES, channels), dtype=np.float32)
        self._steps = np.arange(BLOCK_FRAMES, dtype=np.float64) # 0, 1, 2, ... output samples into the block
        self._read_pos = np.empty(BLOCK_FRAMES, dtype=np.float64) # fractional song position per output sample
        self._floor = np.empty(BLOCK_FRAMES, dtype=np.float64)
        self._index = np.empty(BLOCK_FRAMES, dtype=np.int64)
        self._next_buf = np.empty((BLOCK_FRAMES, channels), dtype=np.float32)

        self.stream = sd.OutputStream(device=device, samplerate=rate, channels=channels, dtype="float32",
                                      blocksize=BLOCK_FRAMES, latency="low", callback=self._callback)

    def set_gains(self, first_gain, second_gain):
        """Set the target gains; the callback ramps to them over the next block."""
        self.target_gains[0] = float(first_gain)
        self.target_gains[1] = float(second_gain)

    def set_speeds(self, first_speed, second_speed):
        """Set the playback speeds (turntable style: pitch follows speed). Applies from the next block."""
        self.speeds[0] = max(float(first_speed), 0.0)
        self.speeds[1] = max(float(second_speed), 0.0)

    def play_drum(self, index, strength, volume):
        """Play drum `index` once at `gain`. A drum that is still playing is cut off and replaced."""
        s = min(max(strength / DRUM_STRENGTH_MAX, 0.0), 1.0)
        v = min(max(volume / SLIDER_MAX, 0.0), 1.0)
        gain = s * v * v

        self._drum_request = (index, float(gain))

    def play_note(self, direction):
        """Play the forward (1) or backward (-1) note once. A note that is still playing is cut off and replaced."""
        self._note_request = direction

    def set_fork_gain(self, gain):
        """Gain of the tuning fork stream (values are played as they come, so ranges above 1 are louder)."""
        self._fork_gain = float(gain)

    def open_fork(self, sample_rate):
        """Open and start the tuning fork stream at the channel's own rate (WASAPI converts it to the device rate)."""
        self.fork_stream = sd.OutputStream(device=self._device, samplerate=sample_rate, channels=1, dtype="float32",
                                           extra_settings=sd.WasapiSettings(auto_convert=True))
        self.fork_stream.start()

    def play_fork(self, samples):
        """Main thread: queue tuning fork samples for playback (blocks briefly when the stream's buffer is full)."""
        if len(samples) and self.fork_stream is not None:
            self.fork_stream.write((samples * self._fork_gain).astype(np.float32))

    def start(self):
        self.stream.start()

    def stop(self):
        self.stream.stop()
        self.stream.close()
        if self.fork_stream is not None:
            self.fork_stream.stop()
            self.fork_stream.close()

    def _callback(self, out, frames, time_info, status):
        out.fill(0)

        for i, song in enumerate(self.songs):
            pos, speed = self.positions[i], self.speeds[i]

            last = len(song) - 2  # k and k + 1 samples needed for linear interpolation.
            if speed > 0:
                n = min(frames, math.floor((last - pos) / speed) + 1)
            else:
                n = frames if pos <= last else 0

            # Check if the song has ended.
            if n <= 0:
                continue

            # Linear gain ramp from the previous gain to the target over this block.
            g0, g1 = self.gains[i], self.target_gains[i] # where we are, where we want to be

            # Compute the gain.
            gain = self._gain_buf[:n]
            np.multiply(self._ramp[:n], g1 - g0, out=gain)
            gain += g0

            # Read the song at pos, pos + speed, pos + 2·speed, ... with linear interpolation.
            read_pos = self._read_pos[:n]
            np.multiply(self._steps[:n], speed, out=read_pos)
            read_pos += pos
            floor = self._floor[:n]
            np.floor(read_pos, out=floor)
            index = self._index[:n]
            index[:] = floor
            read_pos -= floor

            mix = self._mix_buf[:n]
            np.take(song, index, axis=0, out=mix, mode="clip")  # song[k]
            index += 1
            nxt = self._next_buf[:n]
            np.take(song, index, axis=0, out=nxt, mode="clip")  # song[k + 1]
            nxt -= mix
            nxt *= read_pos[:, None]
            mix += nxt  # song[k] + fraction · (song[k + 1] - song[k])

            # Scale this block of the song and add it to the mix.
            mix *= gain[:, None]
            out[:n] += mix

            # Adjust the values for the next block.
            self.gains[i] = g1
            self.positions[i] = pos + n * speed

        # Start a requested drum from the beginning, replacing any drum that is still playing.
        request = self._drum_request
        if request is not None:
            self._drum_request = None
            self._drum = self.drums[request[0]]
            self._drum_gain = request[1]
            self._drum_pos = 0

        # Mix the playing drum on top of the songs.
        if self._drum is not None:
            drum, pos = self._drum, self._drum_pos
            n = min(frames, len(drum) - pos)
            mix = self._mix_buf[:n]
            np.multiply(drum[pos:pos + n], self._drum_gain, out=mix)
            out[:n] += mix

            self._drum_pos = pos + n
            if self._drum_pos >= len(drum):
                self._drum = None

        # Start a requested note from the beginning, replacing any note that is still playing.
        request = self._note_request
        if request is not None:
            self._note_request = None
            self._note = self.notes[request]
            self._note_pos = 0

        # Mix the playing note on top.
        if self._note is not None:
            note, pos = self._note, self._note_pos
            n = min(frames, len(note) - pos)
            out[:n] += note[pos:pos + n]

            self._note_pos = pos + n
            if self._note_pos >= len(note):
                self._note = None


def _find_wasapi_output():
    """Default WASAPI output device. Returns (device_index, sample_rate, channels), channels at most 2 (stereo)."""

    wasapi = next(i for i, h in enumerate(sd.query_hostapis()) if "WASAPI" in h["name"])
    device = sd.query_hostapis(wasapi)["default_output_device"]
    info = sd.query_devices(device)
    return device, int(info["default_samplerate"]), min(2, info["max_output_channels"])


def _load_audio(path, rate, channels):
    """Load an audio file as float32 (frames, channels), resampled to `rate` by linear interpolation."""

    clip, clip_rate = sf.read(path, dtype="float32", always_2d=True)
    channel_count = clip.shape[1]

    # Adjust sample rate to the device sample rate.
    if clip_rate != rate:
        new_sample_count = int(len(clip) * rate / clip_rate)
        original_timestamps = np.arange(len(clip)) / clip_rate
        new_timestamps = np.arange(new_sample_count) / rate

        # Resample each channel.
        resampled = np.empty((new_sample_count, channel_count), dtype=np.float32)

        for c in range(channel_count):
            resampled[:, c] = np.interp(new_timestamps, original_timestamps, clip[:, c])

        clip = resampled

    if channel_count < channels:
        clip = np.repeat(clip, channels, axis=1)

    return np.ascontiguousarray(clip[:, :channels])
