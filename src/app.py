import time

from src.dsremote import DSRemoteSession
from src.sound_player import SoundPlayer
from src.utils.util import EXIT_OK

CHANNELS = ["Master"]


class DJStudioApp:
    def __init__(self, config, host, cmd_port, data_port):
        self.config = config
        self.host = host
        self.cmd_port = cmd_port
        self.data_port = data_port

    def run(self):
        player = None

        if self.config.mode == "music_mix":
            player = SoundPlayer(self.config.first_song["path"], self.config.second_song["path"], 1.0, 0.0)

        try:
            with DSRemoteSession(self.host, self.cmd_port, self.data_port) as session:
                channels = session.open_channels(CHANNELS)
                session.start(1024)

                if player:
                    player.start()

                # Test Master acquisition.
                ai4 = channels["Master"]
                while True:
                    time.sleep(0.005)
                    samples, stamps = session.read(ai4)
                    if not len(samples):
                        continue

                    print("t=%.5f..%.5f  n=%d  overruns=%d  gaps=%d  %s"
                          % (stamps[0], stamps[-1], len(samples), ai4.overruns, ai4.gaps, samples))
        finally:
            if player:
                player.stop()

        return EXIT_OK
