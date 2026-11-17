import math
import os

import numpy as np
import sounddevice as sd
import soundfile as sf

from src.utils.util import PROJECT_ROOT

BLOCK_FRAMES = 256 # fixed callback block size (~5 ms at 48 kHz)

# Slider value range.
SLIDER_MIN = 0.0
SLIDER_MAX = 100.0

# Drum sounds.
DRUM_DIR = os.path.join(PROJECT_ROOT, "assets", "drums")
DRUM_STRENGTH_MAX = 10.0  # Drum hit strength 1-10.

# Note sounds.
NOTE_DIR = os.path.join(PROJECT_ROOT, "assets", "note")
NOTE_FILES = {1: "forward_note.wav", -1: "backwards_note.wav"}

# Sync click. detected on Master by the C++ songs script.
CLICK_SAMPLES = 48

# Tuning fork stream buffer.
FORK_LATENCY_S = 0.1


class SoundPlayer:
    def __init__(self, first_song_path, second_song_path, first_gain, second_gain):
        device, rate, channels = _find_wasapi_output()
        self._device = device

        # Load both song files into RAM, resampled to the device rate.
        self.songs = [_load_audio(path, rate, channels) for path in (first_song_path, second_song_path)]

        # Songs
        self.song_positions = [0.0, 0.0] # Positions of songs (fractional sample index).
        self.song_speeds = [1.0, 1.0] # Playback speed of each song (1 = original, 0 = stopped)
        self.song_gains = [float(first_gain), float(second_gain)] # the gain each song is playing at right now
        self.song_target_gains = [float(first_gain), float(second_gain)] # the gain each song should ramp to (set by set_gains)

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
        self._note_gain = 0.0
        self._note_request = None

        # Sync click.
        self._click_pending = True

        # Tuning fork (its own stream at the channel rate).
        self.fork_stream = None
        self._fork_gain = 1.0

        # Preallocated buffers for the callback.
        self._ramp = np.arange(1, BLOCK_FRAMES + 1, dtype=np.float32) / BLOCK_FRAMES # Ramp shape 1/256..1: fraction of the way from the old to the new gain, per sample.
        self._gain_buf = np.empty(BLOCK_FRAMES, dtype=np.float32)
        self._mix_buf = np.empty((BLOCK_FRAMES, channels), dtype=np.float32)
        self._steps = np.arange(BLOCK_FRAMES, dtype=np.float64) # 0, 1, 2, ... output samples into the block
        self._read_pos = np.empty(BLOCK_FRAMES, dtype=np.float64) # fractional song position per output sample
        self._whole = np.empty(BLOCK_FRAMES, dtype=np.float64)    # floor (read position)
        self._fraction = np.empty(BLOCK_FRAMES, dtype=np.float64) # read position - floor, 0..1
        self._index = np.empty(BLOCK_FRAMES, dtype=np.int64)
        self._next_buf = np.empty((BLOCK_FRAMES, channels), dtype=np.float32)

        self.stream = sd.OutputStream(device=device, samplerate=rate, channels=channels, dtype="float32",
                                      blocksize=BLOCK_FRAMES, latency="low", callback=self._callback)

    def set_gains(self, first_gain, second_gain):
        """Set the target gains; the callback ramps to them over the next block."""
        self.song_target_gains[0] = float(first_gain)
        self.song_target_gains[1] = float(second_gain)

    def set_speeds(self, first_speed, second_speed):
        """Set the playback speeds (turntable style: pitch follows speed). Applies from the next block."""
        self.song_speeds[0] = max(float(first_speed), 0.0)
        self.song_speeds[1] = max(float(second_speed), 0.0)

    def play_drum(self, index, strength, volume):
        """Play drum `index` once at `gain`. A drum that is still playing is cut off and replaced."""
        s = normalise(strength, DRUM_STRENGTH_MAX)
        v = normalise(volume, SLIDER_MAX)
        gain = s * v * v

        self._drum_request = (index, float(gain))

    def play_note(self, direction, volume):
        """Play the forward (1) or backward (-1) note once at gain v². A note that is still playing is cut off and replaced."""
        self._note_request = (direction, tuning_fork_gain(volume))

    def set_fork_gain(self, gain):
        """Gain of the tuning fork stream (values are played as they come, so ranges above 1 are louder)."""
        self._fork_gain = float(gain)

    def open_fork(self, sample_rate):
        """Open and start the tuning fork stream at the channel's own rate (WASAPI converts it to the device rate)."""
        self.fork_stream = sd.OutputStream(device=self._device, samplerate=sample_rate, channels=1, dtype="float32",
                                           latency=FORK_LATENCY_S, extra_settings=sd.WasapiSettings(auto_convert=True))
        self.fork_stream.start()

    def play_fork(self, samples):
        """Main thread: queue tuning fork samples for playback."""
        if self.fork_stream is None:
            return

        free = self.fork_stream.write_available
        if len(samples) and free:
            self.fork_stream.write((samples[-free:] * self._fork_gain).astype(np.float32))

    def start(self):
        self.stream.start()

    def stop(self):
        # Song stream.
        self.stream.stop()
        self.stream.close()

        # Tuning fork stream.
        if self.fork_stream is not None:
            self.fork_stream.stop()
            self.fork_stream.close()

    def _callback(self, out, frames, time_info, status):
        out.fill(0)

        for i in range(len(self.songs)):
            self._mix_song(i, out, frames)

        self._mix_drum(out, frames)
        self._mix_note(out, frames)

        # Overwrites the mix.
        self._write_sync_click(out)

    def _mix_song(self, i, out, frames):
        """Add the next block of song i: read at its speed, interpolated, with a gain ramp."""
        song, pos, speed = self.songs[i], self.song_positions[i], self.song_speeds[i]

        n = _readable_samples(len(song), pos, speed, frames)
        if n == 0:
            return  # the song has ended

        start_gain, end_gain = self.song_gains[i], self.song_target_gains[i]

        samples = self._read_interpolated(song, pos, speed, n)
        samples *= self._gain_ramp(start_gain, end_gain, n)[:, None]  # same gain for every channel
        out[:n] += samples

        # The next block continues where this one stopped.
        self.song_gains[i] = end_gain
        self.song_positions[i] = pos + n * speed

    def _read_interpolated(self, song, pos, speed, n):
        """n song samples at pos, pos + speed, pos + 2·speed, ... (between two stored samples: linear interpolation).

        value = song[k] + fraction · (song[k + 1] - song[k]),  with k + fraction = read position.
        Returns a view of a preallocated buffer, valid until the next call.
        """

        # read position = pos + j · speed  (j = 0, 1, 2, ... output sample in the block)
        read_pos = self._read_pos[:n]
        np.multiply(self._steps[:n], speed, out=read_pos)
        read_pos += pos

        # k = floor(read position)
        whole = self._whole[:n]
        np.floor(read_pos, out=whole)

        # fraction = read position - k
        fraction = self._fraction[:n]
        np.subtract(read_pos, whole, out=fraction)

        # song[k]
        k = self._index[:n]
        k[:] = whole
        current_sample = self._mix_buf[:n]
        np.take(song, k, axis=0, out=current_sample, mode="clip")

        # song[k + 1]
        k += 1
        following_sample = self._next_buf[:n]
        np.take(song, k, axis=0, out=following_sample, mode="clip")

        # song[k] + fraction · (song[k + 1] - song[k])
        difference = following_sample
        difference -= current_sample
        difference *= fraction[:, None]
        current_sample += difference

        return current_sample

    def _gain_ramp(self, start_gain, end_gain, n):
        """Per-sample gain sliding linearly from start_gain to end_gain over the block (no clicks on changes).

        gain[j] = start_gain + ramp[j] · (end_gain - start_gain),  ramp[j] = (j + 1) / 256  (1/256 .. 1)
        """
        # ramp[j] · (end_gain - start_gain)
        gain = self._gain_buf[:n]
        np.multiply(self._ramp[:n], end_gain - start_gain, out=gain)

        # start_gain + ramp[j] · (end_gain - start_gain)
        gain += start_gain

        return gain

    def _mix_drum(self, out, frames):
        """Start a requested drum (replacing one that is still playing), then add its next block."""
        request = self._drum_request
        if request is not None:
            self._drum_request = None
            self._drum = self.drums[request[0]]
            self._drum_gain = request[1]
            self._drum_pos = 0

        if self._drum is not None:
            self._drum_pos = self._mix_one_shot(self._drum, self._drum_pos, self._drum_gain, out, frames)
            if self._drum_pos >= len(self._drum):
                self._drum = None

    def _mix_note(self, out, frames):
        """Start a requested note (replacing one that is still playing), then add its next block."""
        request = self._note_request
        if request is not None:
            self._note_request = None
            self._note = self.notes[request[0]]
            self._note_gain = request[1]
            self._note_pos = 0

        if self._note is not None:
            self._note_pos = self._mix_one_shot(self._note, self._note_pos, self._note_gain, out, frames)
            if self._note_pos >= len(self._note):
                self._note = None

    def _mix_one_shot(self, sound, pos, gain, out, frames):
        """Add the next block of a sound that plays once (drum, note) at a constant gain. Returns the new position.

        out[j] += gain · sound[pos + j],  j = 0 .. n - 1
        """
        # n = samples left in this block (fewer at the end of the sound)
        n = min(frames, len(sound) - pos)

        # gain · sound[pos + j]
        samples = self._mix_buf[:n]
        np.multiply(sound[pos:pos + n], gain, out=samples)

        # out[j] += gain · sound[pos + j]
        out[:n] += samples

        # next block continues at pos + n
        return pos + n

    def _write_sync_click(self, out):
        """First block only: the sync click that the C++ songs script detects on Master."""
        if self._click_pending:
            self._click_pending = False
            out[:CLICK_SAMPLES] = 100.0


def _readable_samples(song_length, pos, speed, frames):
    """How many output samples of this block can still be read from the song.

    Interpolation reads song[k] and song[k + 1].
    """
    last = song_length - 2

    if pos > last:
        return 0

    if speed == 0:
        return frames  # stopped turntable: keeps playing the current position

    return min(frames, math.floor((last - pos) / speed) + 1)


def normalise(value, maximum):
    """value / maximum, clamped to 0..1."""
    return min(max(value / maximum, 0.0), 1.0)


def mix_gains(mixer, volume):
    """Song gains (gA, gB) from the raw slider values (0..100).

    x = mixer / 100  (0 = only the first song, 1 = only the second song)
    v = volume / 100 (0 = silent, 1 = full)
    gA = v² · cos(x·π/2),  gB = v² · sin(x·π/2)

    Equal-power crossfade: gA² + gB² = v⁴, so the loudness stays constant across the fade.
    v² makes the volume slider feel even along its travel.
    """
    x = normalise(mixer, SLIDER_MAX)
    v = normalise(volume, SLIDER_MAX)
    level = v * v
    return level * math.cos(x * math.pi / 2), level * math.sin(x * math.pi / 2)


def tuning_fork_gain(volume):
    """Gain v² from the raw volume slider value (0..100), as used for the songs."""
    v = normalise(volume, SLIDER_MAX)
    return v * v


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
