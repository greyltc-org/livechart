import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Gio

import random
import importlib.resources
import pathlib

# import sys
# import argparse

from matplotlib.backends.backend_gtk4cairo import FigureCanvas

# from matplotlib.backends.backend_gtk4agg import FigureCanvas
from matplotlib.figure import Figure


class Interface(object):
    app = None
    version = "0.0.0"
    backend_server = "localhost"
    some_widgets = {}
    data = None

    def __init__(self):
        self.app = Gtk.Application(application_id="org.greyltc.livechart", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.app.connect("activate", self.on_app_activate)

        # setup about dialog
        self.ad = Gtk.AboutDialog.new()
        self.ad.props.program_name = "livechart"
        self.ad.props.version = self.version
        self.ad.props.authors = ["Grey Christoforo"]
        self.ad.props.copyright = "(C) 2022 Grey Christoforo"
        self.ad.props.logo_icon_name = "applications-other"

        self.randomize()

    def on_app_activate(self, app):
        win = self.app.props.active_window
        if not win:
            ui_data = self.get_ui_data()
            assert None not in ui_data.values(), "Unable to find UI definition data."

            win_builder = Gtk.Builder()
            if win_builder.add_from_string(ui_data["win"]):
                win = win_builder.get_object("win")  # Gtk.ApplicationWindow
            else:
                raise ValueError("Failed to import main window UI")

            help_overlay_builder = Gtk.Builder()
            if help_overlay_builder.add_from_string(ui_data["help_overlay"]):
                help_overlay = help_overlay_builder.get_object("help_overlay")  # Gtk.ShortcutsWindow
            else:
                raise ValueError("Failed to import help overlay UI")

            self.some_widgets["val"] = win_builder.get_object("val")

            win.set_application(app)
            win.set_help_overlay(help_overlay)
            win.props.title = f"livechart {self.version}"

            # make actions for menu items
            self.create_action("about", self.on_about_action)
            self.create_action("preferences", self.on_preferences_action)

            # connect signals
            win_builder.get_object("conn_btn").connect("clicked", self.on_conn_btn_clicked)
            win_builder.get_object("dsc_btn").connect("clicked", self.on_dsc_btn_clicked)

            # setup drawing
            fig = Figure(figsize=(6, 4), constrained_layout=True)
            self.canvas = FigureCanvas(fig)  # a Gtk.DrawingArea
            win.set_child(self.canvas)
            ax = fig.add_subplot()
            (self.line,) = ax.plot(self.data, "go")
            # self.canvas.connect("resize", self.new_plot)

        self.app.set_accels_for_action("win.show-help-overlay", ["<Control>question"])

        win.present()

        self.ticker_id = GLib.timeout_add_seconds(1, self.tick, None)

    def update_val(self):
        if "val" in self.some_widgets:
            self.some_widgets["val"].props.label = f"Value={self.data[0]:.3f}"

    def randomize(self):
        self.data = [random.random() for x in range(10)]
        self.update_val()

    def new_plot(self, *args):
        self.randomize()
        self.line.set_ydata(self.data)

    def tick(self, *args):
        self.new_plot()
        self.canvas.queue_draw()
        return True

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
        win = self.app.props.active_window
        # setup prefs dialog
        prefs_setup = {}
        pd = Gtk.Dialog.new()
        pd.props.title = "Preferences"
        pd.add_button("OK", Gtk.ResponseType.OK)
        pd.add_button("Cancel", Gtk.ResponseType.CANCEL)
        pd.set_transient_for(win)
        pd.set_default_response(Gtk.ResponseType.OK)
        pd_content = pd.get_content_area()
        pd_content.props.margin_top = 5
        pd_content.props.margin_bottom = 5
        pd_content.props.margin_start = 5
        pd_content.props.margin_end = 5
        pd_content.props.orientation = Gtk.Orientation.HORIZONTAL
        lbl = Gtk.Label.new("<b>Backend Server: </b>")
        lbl.props.use_markup = True
        pd_content.append(lbl)
        server_box = Gtk.Entry.new()
        sbb = server_box.get_buffer()
        sbb.set_text(self.backend_server, -1)
        self.some_widgets["sbb"] = sbb
        server_box.props.placeholder_text = "Server Hostname or IP"
        server_box.props.activates_default = True
        pd_content.append(server_box)
        pd.connect("response", self.on_prefs_response)
        pd.present()

    def on_prefs_response(self, prefs_dialog, response_code):
        if response_code == Gtk.ResponseType.OK:
            self.backend_server = self.some_widgets["sbb"].props.text
        prefs_dialog.destroy()

    def on_conn_btn_clicked(self, widget):
        print("Connect button clicked")

    def on_dsc_btn_clicked(self, widget):
        print("Disconnect button clicked")

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

    def run(self):
        # parser = argparse.ArgumentParser(description="livechart program")
        # args = parser.parse_args()
        self.app.run()


def main():
    iface = Interface()
    iface.run()


if __name__ == "__main__":
    main()
