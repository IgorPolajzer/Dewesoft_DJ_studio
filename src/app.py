import time

from src.dsremote import DSRemoteSession
from src.encoder_mode import EncoderMode
from src.sound_player import SoundPlayer, mix_gains, tuning_fork_gain
from src.utils.util import EXIT_OK

# DSRemote ring buffer per channel.
BUFFER_SAMPLES = 102400
POLL_INTERVAL_S = 0.005 # 5ms.

# Start values.
START_MIXER = 0.0
START_VOLUME = 100.0
START_DRUM = 0.0
DRUM_VOLUME_FACTOR = 0.75
NOTE_VOLUME_FACTOR = 0.5

START_ENCODER_MODE = EncoderMode.NOTE

# DewesoftX data file.
STORE_FILE_FORMAT = "dj_studio_%Y%m%d_%H%M%S.dxd"


class DJStudioApp:
    def __init__(self, config, host, cmd_port, data_port, dcom):
        self.config = config
        self.host = host
        self.cmd_port = cmd_port
        self.data_port = data_port
        self.dcom = dcom

        # Control values.
        self.mixer = START_MIXER
        self.volume = START_VOLUME
        self.drum_selection = START_DRUM
        self.encoder_mode = START_ENCODER_MODE

        self.rpm = None  # latest encoder RPM in BPM mode.
        self.session = None
        self.channels = None
        self.player = None

    def run(self):
        self.player = SoundPlayer(self.config.first_song["path"], self.config.second_song["path"],
                                  *mix_gains(self.mixer, self.volume))
        self.player.set_fork_gain(tuning_fork_gain(self.volume))

        try:
            with DSRemoteSession(self.host, self.cmd_port, self.data_port) as session:
                self.session = session
                self.channels = session.open_channels([
                    self.config.mixer_slider_channel,
                    self.config.volume_slider_channel,
                    self.config.drum_selection_channel,
                    self.config.drum_channel,
                    self.config.encoder_mode_channel,
                    self.config.encoder_channel,
                    self.config.tuning_fork_channel,
                ])

                session.start(BUFFER_SAMPLES)

                # Store before the player starts, so the sync click on Master is in the file.
                self.dcom.start_storing(time.strftime(STORE_FILE_FORMAT))

                if self.player:
                    self.dcom.switch_screen("Measure", "Track overview")
                    self.player.start()
                    self.player.open_fork(self.channels[self.config.tuning_fork_channel].rate)

                while True:
                    try:
                        time.sleep(POLL_INTERVAL_S)
                        self._music()
                        self._drums()
                        self._encoder()
                        self._tuning_fork()
                    except KeyboardInterrupt:
                        break

        finally:
            if self.player:
                self.player.stop()

        return EXIT_OK

    def _music(self):
        """Mixer and volume sliders -> song gains."""
        new_mixer, new_volume = self.mixer, self.volume

        values, _ = self.session.read(self.channels[self.config.mixer_slider_channel])
        if len(values):
            new_mixer = values[-1]

        values, _ = self.session.read(self.channels[self.config.volume_slider_channel])
        if len(values):
            new_volume = values[-1]

        if (new_mixer, new_volume) != (self.mixer, self.volume):
            self.mixer, self.volume = new_mixer, new_volume
            if self.player:
                self.player.set_gains(*mix_gains(self.mixer, self.volume))
                self.player.set_fork_gain(tuning_fork_gain(self.volume))

    def _drums(self):
        """Drum selection (dropdown 0-3) and drum hits (strengths 1-10)."""
        values, _ = self.session.read(self.channels[self.config.drum_selection_channel])
        if len(values):
            self.drum_selection = values[-1]

        values, _ = self.session.read(self.channels[self.config.drum_channel])
        for strength in values:
            if strength < 1:
                continue

            index = int(round(self.drum_selection))
            if self.player and 0 <= index < len(self.player.drums):
                self.player.play_drum(index, strength, (self.volume * DRUM_VOLUME_FACTOR))

    def _encoder(self):
        """Encoder mode (dropdown)."""
        values, _ = self.session.read(self.channels[self.config.encoder_mode_channel])
        if len(values):
            new_mode = EncoderMode(int(round(values[-1])))

            # Leaving BPM mode: songs go back to their original speed.
            if self.encoder_mode == EncoderMode.BPM and new_mode != EncoderMode.BPM:
                self.rpm = None

                if self.player:
                    self.player.set_speeds(1.0, 1.0)

            self.encoder_mode = new_mode

        values, _ = self.session.read(self.channels[self.config.encoder_channel])
        match self.encoder_mode:
            # NOTE: encoder steps (1 forward, -1 backward, 0 nothing).
            case EncoderMode.NOTE:
                for value in values:
                    if value in (1, -1) and self.player:
                        self.player.play_note(int(value), self.volume * NOTE_VOLUME_FACTOR)

            # BPM: encoder RPM.
            case EncoderMode.BPM:
                # Master BPM = encoder RPM.
                if len(values) and values[-1] != self.rpm:
                    self.rpm = values[-1]

                    if self.player:
                        self.player.set_speeds(self.rpm / self.config.first_song["bpm"],
                                               self.rpm / self.config.second_song["bpm"])

    def _tuning_fork(self):
        """Tuning fork channel streamed to the speaker."""
        values, _ = self.session.read(self.channels[self.config.tuning_fork_channel])

        if self.player:
            self.player.play_fork(values)
