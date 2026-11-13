import time

from src.dsremote import DSRemoteSession
from src.sound_player import SoundPlayer, mix_gains
from src.utils.util import EXIT_OK

# DSRemote ring buffer per channel, in samples. The sliders send at most 100 values/s, so any size
# is far more than one 5 ms poll needs. 102400 worked with Master + one slider in tests.
BUFFER_SAMPLES = 102400
POLL_INTERVAL_S = 0.005 # 5ms.

START_MIXER = 0.0
START_VOLUME = 100.0
START_DRUM = 0.0
START_ENCODER_MODE = 0.0
DRUM_VOLUME_FACTOR = 1.5


class DJStudioApp:
    def __init__(self, config, host, cmd_port, data_port):
        self.config = config
        self.host = host
        self.cmd_port = cmd_port
        self.data_port = data_port

        # Control values.
        self.mixer = START_MIXER
        self.volume = START_VOLUME
        self.drum_selection = START_DRUM
        self.encoder_mode = START_ENCODER_MODE

        self.session = None
        self.channels = None
        self.player = None

    def run(self):
        if self.config.mode == "music_mix":
            self.player = SoundPlayer(self.config.first_song["path"], self.config.second_song["path"],
                                      *mix_gains(self.mixer, self.volume))

        try:
            with DSRemoteSession(self.host, self.cmd_port, self.data_port) as session:
                self.session = session
                self.channels = session.open_channels([
                    self.config.mixer_slider_channel,
                    self.config.volume_slider_channel,
                    self.config.drum_selection_channel,
                    self.config.drum_channel,
                    self.config.encoder_mode_channel,
                ])
                session.start(BUFFER_SAMPLES)

                if self.player:
                    self.player.start()

                while True:
                    try:
                        time.sleep(POLL_INTERVAL_S)
                        self._music()
                        self._drums()
                        self._encoder()
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
                print(f"Drum hit (strength level: {strength}).")
                self.player.play_drum(index, strength, (self.volume * DRUM_VOLUME_FACTOR))

    def _encoder(self):
        """Encoder mode (dropdown)."""
        values, _ = self.session.read(self.channels[self.config.encoder_mode_channel])
        if len(values):
            self.encoder_mode = values[-1]
            print(f"Encoder mode: {self.encoder_mode}.")
