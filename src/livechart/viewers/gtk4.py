import importlib.resources
import pathlib
import gi
import sys

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio


class Interface(object):
    app = None

    def __init__(self):
        self.app = Gtk.Application(application_id="org.greyltc.livechart", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.app.connect("activate", self.on_app_activate)

        # setup about dialog
        self.ad = Gtk.AboutDialog.new()
        self.ad.props.program_name = "livechart"
        self.ad.props.version = "0.1.0"
        self.ad.props.authors = ["Grey Christoforo"]
        self.ad.props.copyright = "(C) 2022 Grey Christoforo"
        self.ad.props.logo_icon_name = "org.greyltc.livechart"

    def on_app_activate(self, app):
        win = self.app.props.active_window
        if not win:
            ui_data = self.get_ui_data()
            assert None not in ui_data.values(), "Unable to find UI definition data."
            win = Gtk.Builder.new_from_string(ui_data["win"], -1).get_object("win")  # Gtk.ApplicationWindow
            help_overlay = Gtk.Builder.new_from_string(ui_data["help_overlay"], -1).get_object("help_overlay")  # Gtk.ShortcutsWindow
            win.set_application(app)
            win.set_help_overlay(help_overlay)

        self.app.set_accels_for_action("win.show-help-overlay", ["<Control>question"])

        self.create_action("about", self.on_about_action)
        self.create_action("preferences", self.on_preferences_action)

        win.present()

    def create_action(self, name, callback):
        """Add an Action and connect to a callback"""
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.app.add_action(action)

    def on_about_action(self, widget, _):
        win = self.app.props.active_window
        self.ad.set_transient_for(win)
        self.ad.present()

    def on_preferences_action(self, widget, _):
        print("app.preferences action activated")

    def get_ui_data(self):
        """load the ui files and return them as a dict of big strings"""
        ui_resource_folder_name = "ui4"
        ui_resource_filename_suffix = ".ui.xml"
        ui_resource_filename_prefixes = ["win", "help_overlay"]
        ui_strings = {}

        # not running from a proper packaged install.
        if __package__ in [None, ""]:
            package = False
            parent_dir = pathlib.Path(__file__).parent
            ui_dir = parent_dir / ui_resource_folder_name
        else:
            package = True

        for ui_resource_file_name_prefix in ui_resource_filename_prefixes:
            ui_strings[ui_resource_file_name_prefix] = None
            ui_resource_file_name = ui_resource_file_name_prefix + ui_resource_filename_suffix
            if package:
                ui_strings[ui_resource_file_name_prefix] = importlib.resources.read_text(".".join([__package__, ui_resource_folder_name]), ui_resource_file_name)
            else:
                ui_file = ui_dir / ui_resource_file_name
                if ui_file.is_file() == True:
                    with open(ui_file) as fh:
                        ui_strings[ui_resource_file_name_prefix] = fh.read()

        return ui_strings

    def show(self):
        self.app.run(sys.argv)


def main():
    iface = Interface()
    iface.show()


if __name__ == "__main__":
    main()
