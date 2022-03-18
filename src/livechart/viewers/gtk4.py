import importlib.resources
import pathlib
import gi
import sys

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio


class Interface(object):
    window = None
    app = None
    b = None
    ui_data = None

    def __init__(self):
        self.ui_data = self.get_ui_data()
        assert self.ui_data is not None, "Unable to find UI definition data."

        self.b = Gtk.Builder.new_from_string(self.ui_data, -1)
        b = self.b

        self.window = b.get_object("main_win")
        # win = self.window

        self.app = Gtk.Application(application_id="org.greyltc.livechart", flags=Gio.ApplicationFlags.FLAGS_NONE)
        app = self.app
        app.connect("activate", self.on_app_activate)

    def on_app_activate(self, app):
        win = self.window
        b = self.b

        win.set_application(app)

        self.create_action("about", self.on_about_action)
        self.create_action("preferences", self.on_preferences_action)

        # win = Gtk.ApplicationWindow(application=app)
        # self.window = win

        # win.set_show_menubar(True)

        # kill_btn = self.window = b.get_object("kill_btn")
        # kill_btn.connect("clicked", lambda x: win.close())

        # win.set_child(btn)

        win.present()

    def on_about_action(self, widget, _):
        print("app.about action activated")
        # about = AboutDialog(self.props.active_window)
        # about.present()

    def on_preferences_action(self, widget, _):
        print("app.preferences action activated")

    def get_ui_data(self):
        # load the ui file and return it as a big string
        ui_resource_folder_name = "ui4"
        ui_resource_file_name = "livechart.ui"
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
        self.app.run(sys.argv)


def main():
    iface = Interface()
    iface.show()


if __name__ == "__main__":
    main()
