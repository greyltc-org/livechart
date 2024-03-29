from attr import has
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk, Gio, GObject, Adw

from importlib import resources
from importlib.metadata import version
import pathlib
import collections
import time
from matplotlib.backends.backend_cairo import FigureCanvasCairo, RendererCairo
from matplotlib.figure import Figure
import struct

# from ..lib import Datagetter
# from ..lib import Downsampler

# import sys
# import argparse


class Interface(object):
    app = None
    version = "0.0.0"
    backend_server = "localhost"
    backend_server_port = 58741
    some_widgets = {}
    max_data_length = None  # can be None for unbounded
    data = collections.deque([(float("nan"), float("nan"))], max_data_length)
    t0 = 0
    closing = False

    def __init__(self):
        try:
            self.version = version(__package__.split(".")[0])
        except Exception as e:
            pass  # this is not a package

        self.app = Gtk.Application(application_id="org.greyltc.livechart", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.app.connect("activate", self.on_app_activate)
        self.app.connect("shutdown", self.on_app_shutdown)

        # setup about dialog
        self.ad = Gtk.AboutDialog.new()
        self.ad.props.program_name = "livechart"
        self.ad.props.version = self.version
        self.ad.props.authors = ["Grey Christoforo"]
        self.ad.props.copyright = "(C) 2022 Grey Christoforo"
        self.ad.props.logo_icon_name = "applications-other"

        self.t0 = time.time()
        self.s = Gio.SocketClient.new()
        self.float_size = struct.calcsize("f")

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
            # GObject.Object.connect(self.s, "event", self.handle_socket_client_event)  # need to be careful to call correct connect()

            # setup a toasty drawing area
            self.canvas = Gtk.DrawingArea.new()
            self.canvas.set_draw_func(self.draw_canvas)
            self.tol = Adw.ToastOverlay.new()
            self.tol.set_child(self.canvas)
            win.set_child(self.tol)

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

    # def handle_socket_client_event(self, socket_client, event, network_address, data):
    #    print(event)

    def draw_canvas(self, canvas, ctx, lenx, leny):
        self.fcc.set_size_inches(lenx / self.dpi, leny / self.dpi)

        self.renderer.set_ctx_from_surface(ctx.get_target())
        self.renderer.set_width_height(lenx, leny)

        self.fcc.draw(self.renderer)

    def update_val(self):
        if "val" in self.some_widgets:
            self.some_widgets["val"].props.label = f"Value={self.data[0][1]:.3f}"

    def handle_data(self, input_stream, result):
        if (not input_stream.props.socket.is_closed()) and (not self.closing):
            try:
                vraw = input_stream.read_bytes_finish(result)
                dat = struct.unpack("f", vraw.unref_to_data())[0]
                input_stream.read_bytes_async(self.float_size, GLib.PRIORITY_DEFAULT, None, self.handle_data)
            except Exception as e:
                toast = Adw.Toast.new(f"Closing connection because of data reception failure: {e}")
                toast.props.timeout = 3
                self.tol.add_toast(toast)
                self.close_conn()
            else:
                self.data.appendleft((time.time() - self.t0, dat))
                self.update_val()
                self.new_plot()
                self.canvas.queue_draw()

    def new_plot(self, *args):
        x = [d[0] for d in self.data]
        y = [d[1] for d in self.data]
        self.line.set_xdata(x)
        self.line.set_ydata(y)
        self.ax.autoscale(enable=True, axis="x", tight=True)
        self.ax.autoscale(enable=True, axis="y", tight=False)
        self.ax.relim()

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
            sbb_txt = self.some_widgets["sbb"].props.text
            sbb_txt_split = sbb_txt.split(":")
            self.backend_server = sbb_txt_split[0]
            if len(sbb_txt_split) > 1:
                self.backend_server_port = int(sbb_txt_split[1])
        prefs_dialog.destroy()

    def on_connect(self, socket_client, result):
        try:
            conn = socket_client.connect_to_host_finish(result)
            conn.props.graceful_disconnect = True
            conn.props.socket.set_timeout(1)
            conn.props.input_stream.read_bytes_async(self.float_size, GLib.PRIORITY_DEFAULT, None, self.handle_data)
            self.conn = conn
        except Exception as e:
            if hasattr(e, "message"):
                toast_text = e.message
            else:
                toast_text = f"{e}"
            toast = Adw.Toast.new(toast_text)
            toast.props.timeout = 3
            self.tol.add_toast(toast)

    def on_conn_btn_clicked(self, widget):
        if hasattr(self, "conn") and (not self.conn.props.closed):
            toast = Adw.Toast.new("Already connected!")
            toast.props.timeout = 3
            self.tol.add_toast(toast)
        else:
            self.s.connect_to_host_async(self.backend_server, self.backend_server_port, None, self.on_connect)

    def on_dsc_btn_clicked(self, widget):
        self.close_conn()

    def close_conn(self):
        if hasattr(self, "conn"):
            try:
                self.closing = True
                self.conn.close_async(GLib.PRIORITY_DEFAULT, None, self.handle_close)
            except Exception as e:
                pass
        else:
            toast = Adw.Toast.new("Not connected.")
            toast.props.timeout = 3
            self.tol.add_toast(toast)

    def handle_close(self, io_stream, result):
        self.closing = False
        try:
            success = io_stream.close_finish(result)
            if success:
                toast_text = "Connection closed."
                del self.conn
            else:
                toast_text = "Connection not closed."
        except Exception as e:
            if hasattr(e, "message"):
                toast_text = f"Problem closing connection: {e.message}"
            else:
                toast_text = f"Problem closing connection: {e}"
        toast = Adw.Toast.new(toast_text)
        toast.props.timeout = 3
        self.tol.add_toast(toast)

    def on_app_shutdown(self, app):
        self.close_conn()

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
