import gi
import importlib.resources
import pathlib

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class Interface(object):
    window = None
    b = None
    ui_data = None

    def __init__(self):
        self.ui_data = self.get_ui_data()
        assert self.ui_data is not None, "Unable to find UI definition data."

        self.b = Gtk.Builder.new_from_string(self.ui_data, -1)
        b = self.b

        self.window = b.get_object("main_win")
        win = self.window

        win.connect("destroy", Gtk.main_quit)

    def get_ui_data(self):
        # load the ui file
        ui_resource_folder_name = "ui3"
        ui_resource_file_name = "livechart.cmb.ui"
        ui_string = None
        if __package__ in [None, ""]:  # not running from a proper packaged install. try to find the ui file anyway
            parent_dir = pathlib.Path(__file__).parent
            ui_file = parent_dir / ui_resource_folder_name / ui_resource_file_name
            if ui_file.is_file() == True:
                with open(ui_file) as fh:
                    ui_string = fh.read()
        else:
            ui_string = importlib.resources.read_text(".".join([__package__, ui_resource_folder_name]), ui_resource_file_name)

        return ui_string

    def show(self):
        self.window.show()


def main():
    iface = Interface()
    iface.show()
    Gtk.main()


if __name__ == "__main__":
    main()
