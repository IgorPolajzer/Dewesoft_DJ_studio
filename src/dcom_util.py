from win32com.client import Dispatch

class DcomUtil:

    def __init__(self):
        self.app = Dispatch("Dewesoft.App")


    def __del__(self):
        self.app = None


    def switch_screen(self, mode, display):
        self.app.SetMainToolBar(mode, display)

    def freeze_screen(self, freeze):
        self.app.SetFreezeMode(freeze)

    def start_storing(self, file_name):
        """Start writing the running measurement to `file_name` (a bare name lands in the DewesoftX data directory)."""
        if not self.app.Acquiring:
            raise RuntimeError("DewesoftX is not acquiring, cannot start storing.")
        self.app.StartStoring(file_name)
