from src.dsremote import DSRemoteSession

# Process exit codes for the caller.
EXIT_OK = 0
EXIT_NOT_OK = 1

CHANNELS = ["AI 4", "Crossfade"]


class DJStudioApp:
    def __init__(self, host, cmd_port, data_port):
        self.host = host
        self.cmd_port = cmd_port
        self.data_port = data_port

    def run(self):
        with DSRemoteSession(self.host, self.cmd_port, self.data_port) as session:
            channels = session.open_channels(CHANNELS)

            session.start(1024)
            samples, stamps = session.read(channels["AI 4"])

            print(channels)
            print(samples, stamps)
            # Switch to Track overview screen
            pass

        return EXIT_OK
