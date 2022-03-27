import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Gio

import random
from importlib import resources
from importlib.metadata import version
import pathlib
import collections
import time
from matplotlib.backends.backend_cairo import FigureCanvasCairo, RendererCairo
from matplotlib.figure import Figure

from ..lib import Datagetter
from ..lib import Downsampler

# import sys
# import argparse


class Interface(object):
    app = None
    version = "0.0.0"
    backend_server = "localhost"
    some_widgets = {}
    max_data_length = None  # can be None for unbounded
    data = collections.deque([(float("nan"), float("nan"))], max_data_length)
    t0 = 0

    def __init__(self):
        try:
            self.version = version(__package__.split(".")[0])
        except Exception as e:
            pass  # this is not a package

        self.app = Gtk.Application(application_id="org.greyltc.livechart", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.app.connect("activate", self.on_app_activate)

        # setup about dialog
        self.ad = Gtk.AboutDialog.new()
        self.ad.props.program_name = "livechart"
        self.ad.props.version = self.version
        self.ad.props.authors = ["Grey Christoforo"]
        self.ad.props.copyright = "(C) 2022 Grey Christoforo"
        self.ad.props.logo_icon_name = "applications-other"

        self.t0 = time.time()

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

            # setup the drawing area
            self.canvas = Gtk.DrawingArea.new()
            self.canvas.set_draw_func(self.draw_canvas)
            win.set_child(self.canvas)

            # setup plot
            fig = Figure(constrained_layout=True)
            self.dpi = fig.get_dpi()
            self.fcc = FigureCanvasCairo(fig).figure
            self.renderer = RendererCairo(self.dpi)
            self.ax = self.fcc.add_subplot()
            self.ax.autoscale(enable=True, axis="x", tight=True)
            self.ax.autoscale(enable=True, axis="y", tight=False)
            self.ax.set_xlabel("Time [s]")
            self.ax.set_ylabel("Value")

        (self.line,) = self.ax.plot(*zip(*self.data), "go")

        self.app.set_accels_for_action("win.show-help-overlay", ["<Control>question"])

        win.present()

        self.ticker_id = GLib.timeout_add_seconds(1, self.tick, None)

    def draw_canvas(self, canvas, ctx, lenx, leny):
        self.fcc.set_size_inches(lenx / self.dpi, leny / self.dpi)

        self.renderer.set_ctx_from_surface(ctx.get_target())
        self.renderer.set_width_height(lenx, leny)

        self.fcc.draw(self.renderer)

    def update_val(self):
        if "val" in self.some_widgets:
            self.some_widgets["val"].props.label = f"Value={self.data[0][1]:.3f}"

    def new_data(self):
        self.data.appendleft((time.time() - self.t0, random.random()))
        self.update_val()

    def new_plot(self, *args):
        self.new_data()
        x = [d[0] for d in self.data]
        y = [d[1] for d in self.data]
        self.line.set_xdata(x)
        self.line.set_ydata(y)
        self.ax.autoscale(enable=True, axis="x", tight=True)
        self.ax.autoscale(enable=True, axis="y", tight=False)
        self.ax.relim()

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
            resource_path = ".".join([__package__, ui_resource_folder_name])

        for ui_resource_file_name_prefix in ui_resource_filename_prefixes:
            ui_strings[ui_resource_file_name_prefix] = None
            ui_resource_file_name = ui_resource_file_name_prefix + ui_resource_filename_suffix
            if package:
                ui_strings[ui_resource_file_name_prefix] = resources.read_text(resource_path, ui_resource_file_name)
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
