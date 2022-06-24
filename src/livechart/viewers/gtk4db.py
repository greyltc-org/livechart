from concurrent.futures import thread
import queue
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

from livechart.db import DBTool
import psycopg
import asyncio
import threading


class Interface(object):
    app = None
    version = "0.0.0"
    db_url = "postgresql://"
    some_widgets = {}
    max_data_length = 700  # can be None for unbounded
    data = collections.deque([(float("nan"), float("nan"))], max_data_length)
    t0 = 0
    closing = False
    async_loops = []
    threads = []
    channels: list[str] = []  # channels to listen to
    all_channels: list[str] = ["no channels"]  # all possible channels
    channel_list: Gtk.ListBox

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

            # collect widgets we'll need to reference later
            self.some_widgets["val"] = win_builder.get_object("val")
            self.some_widgets["conn_btn"] = win_builder.get_object("conn_btn")

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
            self.ax.grid("on")
            (self.line,) = self.ax.plot(*zip(*self.data), "go")
            self.app.set_accels_for_action("win.show-help-overlay", ["<Control>question"])

            # self.cq = asyncio.Queue()
            # event to signal end of db connection
            # self.terminate_db = threading.Event()

        win.present()

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
                if hasattr(e, "message"):
                    toast_text = f"Closing connection because of data reception failure: {e.message}"
                else:
                    toast_text = f"Closing connection because of data reception failure: {e}"
                toast = Adw.Toast.new(toast_text)
                toast.props.timeout = 3
                self.tol.add_toast(toast)
                self.close_conn()
                self.new_plot()
                self.canvas.queue_draw()

    def handle_db_data(self, vals):
        for v in vals:
            if "raw" in v["channel"]:
                # self.data.appendleft((v["t"], v["i"] * v["v"]))
                self.data.appendleft((v["t"], v["v"]))
            elif "runs" in v["channel"]:
                run_msg = f"New Run by {v['user_id']}: {v['name']}"
                toast = Adw.Toast.new(run_msg)
                toast.props.timeout = 1
                self.tol.add_toast(toast)
                print(f"new run: ")
            elif "events" in v["channel"]:
                if v["complete"]:
                    what = "done."
                else:
                    what = "started."
                msg = f"{v['kind']} {what}"
                toast = Adw.Toast.new(msg)
                toast.props.timeout = 1
                self.tol.add_toast(toast)

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

    def fetch_channels(self, button: Gtk.Button):
        """update listen/notify channel list"""
        query = "select event_object_schema, event_object_table from information_schema.triggers where event_manipulation = 'INSERT'"
        fetched_channels = []
        db_url = self.some_widgets["sbb"].props.text
        try:
            with psycopg.connect(db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query)
                    for record in cur:
                        if len(record) == 2:
                            fetched_channels.append(f"{record[0]}_{record[1]}")
        except Exception as e:
            print(f"Faulure to fetch channel list: {e}")
        else:
            if fetched_channels != []:
                self.all_channels = fetched_channels
                self.update_channel_list()

        return None

    def update_channel_list(self):
        # clear the list
        while True:
            try:
                self.channel_list.remove(self.channel_list.get_first_child())
            except:
                break

        for chan in self.all_channels:
            chan_row = Gtk.ListBoxRow()
            label = Gtk.Label.new(chan)
            chan_row.props.child = label
            self.channel_list.append(chan_row)

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
        # pd_content.props.orientation = Gtk.Orientation.HORIZONTAL

        box_spacing = 5

        outerbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, box_spacing)
        pd_content.append(outerbox)

        urllinebox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, box_spacing)
        lbl = Gtk.Label.new("<b>Datbase connection URL: </b>")
        lbl.props.use_markup = True
        urllinebox.append(lbl)
        server_box = Gtk.Entry.new()
        sbb = server_box.get_buffer()
        sbb.set_text(self.db_url, -1)
        self.some_widgets["sbb"] = sbb
        server_box.props.placeholder_text = "postgresql://"
        server_box.props.activates_default = True
        urllinebox.append(server_box)
        outerbox.append(urllinebox)

        refresh_listen = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, box_spacing)
        lcb = Gtk.Button.new_with_label("(Re)Load listen channels")
        lcb.props.hexpand = True
        lcb.connect("clicked", self.fetch_channels)
        refresh_listen.append(lcb)
        outerbox.append(refresh_listen)

        chanlinebox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, box_spacing)
        chan_lbl = Gtk.Label.new("<b>Select Listen Channels: </b>")
        chan_lbl.props.use_markup = True
        chanlinebox.append(chan_lbl)
        self.channel_list = Gtk.ListBox.new()
        self.channel_list.props.selection_mode = Gtk.SelectionMode.MULTIPLE
        self.channel_list.props.hexpand = True
        self.channel_list.props.show_separators = True
        self.channel_list.props.activate_on_single_click = False
        self.update_channel_list()
        chanlinebox.append(self.channel_list)
        outerbox.append(chanlinebox)

        pd.connect("response", self.on_prefs_response)
        pd.present()

    def on_prefs_response(self, prefs_dialog, response_code):
        if response_code == Gtk.ResponseType.OK:
            self.db_url = self.some_widgets["sbb"].props.text
            self.channels = []

            def fill_channels(box: Gtk.ListBox, row: Gtk.ListBoxRow):
                self.channels.append(row.props.child.props.label)

            self.channel_list.selected_foreach(fill_channels)
        prefs_dialog.destroy()

    def thread_task_runner(self):
        """gets run in a new thread"""

        async def q_getter(q):
            while True:
                if q.qsize() > 1:
                    vals = [await q.get() for x in range(q.qsize())]
                else:
                    vals = (await q.get(),)
                GLib.idle_add(self.handle_db_data, vals)

        async def db_listener():
            self.async_loops.append(asyncio.get_running_loop())
            dbw = DBTool(db_uri=self.db_url)
            # listen_channels = []
            # listen_channels.append("org_greyltc_raw_s1738994")
            # listen_channels.append("org_greyltc_tbl_runs")
            # listen_channels.append("org_greyltc_tbl_events")
            # listen_channels.append("org_greyltc_raw_s71c9f7e")
            dbw.listen_channels = self.channels
            aconn = None
            try:
                aconn = await asyncio.create_task(psycopg.AsyncConnection.connect(conninfo=dbw.db_uri, autocommit=True), name="connect")
                await aconn.set_read_only(True)
                toast_text = f"Connected to {dbw.db_uri}"
            except Exception as e:
                if hasattr(e, "message"):
                    toast_text = f"Connection failure: {e.message}"
                else:
                    toast_text = f"Connection failure: {e}"
            toast = Adw.Toast.new(toast_text)
            toast.props.timeout = 3
            self.tol.add_toast(toast)

            if hasattr(aconn, "closed") and (not aconn.closed):
                async with aconn:
                    async with aconn.cursor() as acur:
                        q_task = asyncio.create_task(q_getter(dbw.outq), name="q")
                        listen_task = asyncio.create_task(dbw.new_listening(aconn, acur), name="listen")

                        try:
                            await listen_task
                        except asyncio.CancelledError:
                            pass
                        except Exception as e:
                            print(e)

                        try:
                            await q_task
                        except asyncio.CancelledError:
                            pass
                        except Exception as e:
                            print(e)

                        await asyncio.gather(*[acur.execute(f"UNLISTEN {ch}") for ch in dbw.listen_channels])
                        await aconn.commit()

        asyncio.run(db_listener())
        GLib.idle_add(self.cleanup_conn)

    def on_conn_btn_clicked(self, widget):
        widget.props.sensitive = False
        # TODO: switch from threading here to proper await/async when pygobject supports it
        # see https://gitlab.gnome.org/GNOME/pygobject/-/merge_requests/189
        t = threading.Thread(target=self.thread_task_runner)
        t.daemon = False  # False might cause exit issues when problems arise
        t.start()
        self.threads.append(t)

    def on_dsc_btn_clicked(self, widget):
        self.ask_async_loop_to_finish(fail_toast=True)

    def ask_async_loop_to_finish(self, fail_toast: bool = False):
        signal_sent = False
        for loop in self.async_loops:
            if not loop.is_closed():
                for task in asyncio.all_tasks(loop):
                    if task.get_name() in ["connect", "q", "listen"]:
                        signal_sent = True
                        loop.call_soon_threadsafe(task.cancel)  # ask the things keeping the loop running to stop

        if (not signal_sent) and fail_toast:
            toast = Adw.Toast.new("No connection to close.")
            toast.props.timeout = 3
            self.tol.add_toast(toast)

    def cleanup_conn(self):
        # clean up the async loop(s) and their thread(s)
        # there should really only ever be one thread and one loop here in reality

        self.ask_async_loop_to_finish(fail_toast=False)
        toast_text = "No connection to close."

        for thread in self.threads:
            try:
                thread.join(timeout=5)
                toast_text = "Connection closed."
            except Exception as e:
                print(e)
            finally:
                if thread.is_alive():
                    toast_text = f"Failure joining thread: {thread}"

        for i, thread in enumerate(self.threads):
            del self.threads[i]

        for i, loop in enumerate(self.async_loops):
            del self.async_loops[i]

        self.some_widgets["conn_btn"].props.sensitive = True

        toast = Adw.Toast.new(toast_text)
        toast.props.timeout = 3
        self.tol.add_toast(toast)

    def on_app_shutdown(self, app):
        self.cleanup_conn()

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
