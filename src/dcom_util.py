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
