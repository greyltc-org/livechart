from concurrent.futures import thread
import queue
import gi
import pygal
from pygal.style import LightSolarizedStyle

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Rsvg", "2.0")
from gi.repository import GLib, Gtk, Gio, GObject, Adw, Gdk, GdkPixbuf, Rsvg


from importlib import resources
from importlib.metadata import version
import pathlib
import collections
import time

# from matplotlib.backends.backend_cairo import FigureCanvasCairo, RendererCairo
# from matplotlib.figure import Figure
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
    max_data_length = 1000  # can be None for unbounded
    data = collections.deque([(float("nan"), float("nan"))], max_data_length)
    t0 = 0
    closing = False
    async_loops = []
    threads = []
    channels: list[str] = []  # channels to listen to
    all_channels: list[str] = ["no channels"]  # all possible channels
    channel_list: Gtk.ListBox
    sparkline_x = 500
    sparkline_y = 50
    raw_channels = []
    charts = {}
    lb = {}  # latest bytes
    das = {}

    def __init__(self):
        try:
            self.version = version(__package__.split(".")[0])
        except Exception as e:
            pass  # this is not a package

        app_id = "org.greyltc.livechart"
        self.app = Gtk.Application(application_id=app_id, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.app.connect("activate", self.on_app_activate)
        self.app.connect("shutdown", self.on_app_shutdown)

        self.settings = Gio.Settings.new(app_id)
        self.db_url = self.settings.get_string("address")

        # setup about dialog
        self.ad = Gtk.AboutDialog.new()
        self.ad.props.program_name = "livechart"
        self.ad.props.version = self.version
        self.ad.props.authors = ["Greyson Christoforo"]
        self.ad.props.copyright = "(C) 2022 Grey Christoforo"
        self.ad.props.logo_icon_name = "applications-other"

        self.t0 = time.time()
        self.s = Gio.SocketClient.new()
        self.float_size = struct.calcsize("f")
        # self.chart = pygal.XY(style=LightSolarizedStyle)
        # self.chart.add("", [1, 3, 5, 16, 13, 3, 7, 9, 2, 1, 4, 9, 12, 10, 12, 16, 14, 12, 7, 2])
        # self.chart.add("", [])

    def on_app_activate(self, app):
        win = self.app.props.active_window
        if not win:
            win = Gtk.ApplicationWindow.new(app)
            win.props.default_height = 300
            win.props.default_width = 600
            tb = Gtk.HeaderBar.new()
            mb = Gtk.MenuButton.new()
            mb.props.primary = True
            mb.props.icon_name = "open-menu-symbolic"
            menu = Gio.Menu.new()
            sub_menu = Gio.Menu.new()
            sub_menu.append("_Preferences", "app.preferences")
            # sub_menu.append("_Keyboard Shortcuts", "win.show-help-overlay")
            sub_menu.append("_About livechart", "app.about")
            # menu_section = Gio.MenuItem.new_section(None, sub_menu)
            menu.append_section(None, sub_menu)
            # menu.append_item(menu_section)
            mb.props.menu_model = menu
            tb.pack_end(mb)

            cbtn = Gtk.Button.new_from_icon_name("call-start")
            cbtn.connect("clicked", self.on_conn_btn_clicked)
            cbtn.props.tooltip_markup = "Connect to backend"
            tb.pack_start(cbtn)

            dbtn = Gtk.Button.new_from_icon_name("call-stop")
            dbtn.connect("clicked", self.on_dsc_btn_clicked)
            dbtn.props.tooltip_markup = "Disconnect from backend"
            tb.pack_start(dbtn)

            lbl = Gtk.Label.new("Value=")
            tb.pack_start(lbl)

            win.props.titlebar = tb

            # help_overlay_builder = Gtk.Builder()
            # if help_overlay_builder.add_from_string(ui_data["help_overlay"]):
            #    help_overlay = help_overlay_builder.get_object("help_overlay")  # Gtk.ShortcutsWindow
            # else:
            #    raise ValueError("Failed to import help overlay UI")

            # collect widgets we'll need to reference later
            self.some_widgets["val"] = lbl
            self.some_widgets["conn_btn"] = cbtn

            win.set_application(app)
            # win.set_help_overlay(help_overlay)
            win.props.title = f"livechart {self.version}"

            # make actions for menu items
            self.create_action("about", self.on_about_action)
            self.create_action("preferences", self.on_preferences_action)

            # connect signals
            # GObject.Object.connect(self.s, "event", self.handle_socket_client_event)  # need to be careful to call correct connect()

            # pixbuf stuff
            # self.pbls = {0: GdkPixbuf.PixbufLoader.new_with_type("svg")}
            # self.pbls_init = {0: False}
            # self.pbls_animi = {}
            # pbli = 0
            # GObject.Object.connect(self.pbls[pbli], "area-prepared", self.pbl_area_prepared, pbli)
            # GObject.Object.connect(self.pbls[pbli], "size-prepared", self.pbl_size_prepared, pbli)

            # setup a toasty drawing area
            # self.canvas = Gtk.DrawingArea.new()
            # self.canvas.set_draw_func(self.draw_canvas, 0)
            self.tol = Adw.ToastOverlay.new()
            self.main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
            self.main_box.props.vexpand = True
            self.main_box.props.vexpand_set = True
            # self.set_homogeneous = True
            # self.main_box.append(self.canvas)
            # self.main_box.append(Gtk.Label.new("Hai!"))
            self.tol.set_child(self.main_box)
            # self.tol.set_child(self.canvas)
            win.set_child(self.tol)

            # setup plot
            # fig = Figure(constrained_layout=True)
            # self.dpi = fig.get_dpi()
            # self.fcc = FigureCanvasCairo(fig).figure
            # self.renderer = RendererCairo(self.dpi)
            # self.ax = self.fcc.add_subplot()
            # self.ax.autoscale(enable=True, axis="x", tight=True)
            # self.ax.autoscale(enable=True, axis="y", tight=False)
            # self.ax.set_xlabel("Time [s]")
            # self.ax.set_ylabel("Value")
            # self.ax.grid("on")
            # (self.line,) = self.ax.plot(*zip(*self.data), "go")
            # self.app.set_accels_for_action("win.show-help-overlay", ["<Control>question"])

            # self.cq = asyncio.Queue()
            # event to signal end of db connection
            # self.terminate_db = threading.Event()

            # chart_bytes = self.chart.render_sparkline(width=self.sparkline_x, height=self.sparkline_y, show_dots=False, show_y_labels=True)
            # self.pbls[pbli].write_bytes(GLib.Bytes.new_take(chart_bytes))
            # self.pbls[pbli].close()

        win.present()

    def pbl_area_prepared(self, pb_loader, user_data):
        if not self.pbls_init[user_data]:
            self.pbls_init[user_data] = True
            self.pbls_animi[user_data] = pb_loader.get_animation().get_iter()
        self.canvas.set_draw_func(self.draw_canvas, user_data)
        self.canvas.queue_draw()

    def pbl_size_prepared(self, pb_loader, size_x, size_y, user_data):
        pass
        # self.canvas.queue_draw()

    def draw_canvas(self, canvas, ctx, lenx, leny, user_data):
        # self.fcc.set_size_inches(lenx / self.dpi, leny / self.dpi)

        # t = Gdk.Texture.new_from_file(Gio.File.new_for_path("/tmp/svg"))
        # pb = GdkPixbuf.Pixbuf.new_from_file_at_scale("/tmp/svg", -1, 125, True)
        # chart_bytes = self.chart.render_sparkline(width=500, height=50, show_dots=False, show_y_labels=True)
        # self.pbl.write_bytes(GLib.Bytes.new_take(chart_bytes))
        st = Gio.MemoryInputStream.new_from_bytes(self.lb[user_data])
        pb = GdkPixbuf.Pixbuf.new_from_stream_at_scale(st, lenx, -1, True)
        Gdk.cairo_set_source_pixbuf(ctx, pb, 0, 0)

        # self.pbls_animi[user_data]
        # pb = self.pbl.get_pixbuf()
        # pb = self.pbls_animi[user_data].get_pixbuf()
        # if pb is not None:
        #    Gdk.cairo_set_source_pixbuf(ctx, pb, 0, 0)

        # self.renderer.set_ctx_from_surface(ctx.get_target())
        # self.renderer.set_width_height(lenx, leny)

        # self.fcc.draw(self.renderer)
        ctx.paint()

    def update_val(self, val, i):
        if "val" in self.some_widgets:
            self.some_widgets["val"].props.label = f"Value{i}={val:.3f}"

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
                # self.new_plot()
                # self.canvas.queue_draw()

    def handle_db_data(self, vals):
        for v in vals:
            if "raw" in v["channel"]:
                new_chan = False
                if v["channel"] not in self.raw_channels:
                    new_chan = True
                    self.raw_channels.append(v["channel"])
                    self.raw_channels = sorted(self.raw_channels)
                i = self.raw_channels.index(v["channel"])
                if new_chan:
                    nda = Gtk.DrawingArea.new()
                    nda.props.height_request = self.sparkline_y + 10
                    # nda.props.vexpand = True
                    # nda.props.vexpand_set = True
                    nda.set_draw_func(self.draw_canvas, len(self.raw_channels) - 1)
                    # self.canvas.set_draw_func(self.draw_canvas, len(self.raw_channels) - 1)
                    self.main_box.append(nda)
                if i not in self.charts:
                    self.charts[i] = pygal.XY(style=LightSolarizedStyle)
                    self.charts[i].add("", [])

                # self.data.appendleft((v["t"], v["i"] * v["v"]))
                # self.data.appendleft((v["t"], v["v"]))
                newv = v["v"]
                newt = v["t"]
                chart_data = self.charts[i].raw_series[0][0]
                if len(chart_data) >= self.max_data_length:
                    chart_data.pop(0)
                chart_data.append((newt, newv))
                self.update_val(v["v"], i)
                # store latest chart bytes
                self.lb[i] = GLib.Bytes.new_take(self.charts[i].render_sparkline(width=self.sparkline_x, height=self.sparkline_y, show_dots=False, show_y_labels=True))

                # self.das[i].queue_draw()
                # self.canvas.queue_draw()
                for k, c in enumerate(self.main_box):
                    if k == i:
                        c.queue_draw()
                        break

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

        # self.update_val(v["v"], i)
        # self.new_plot()
        # chart_bytes = self.charts[i].render_sparkline(width=self.sparkline_x, height=self.sparkline_y, show_dots=False, show_y_labels=True)
        # self.pbls[0].write_bytes(GLib.Bytes.new_take(chart_bytes))
        # self.pbls[0].close()

    def new_plot(self, *args):
        # x = [d[0] for d in self.data]
        y = [d[1] for d in self.data]

        # self.line.set_xdata(x)
        # self.line.set_ydata(y)
        # self.ax.autoscale(enable=True, axis="x", tight=True)
        # self.ax.autoscale(enable=True, axis="y", tight=False)
        # self.ax.relim()

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
                self.settings.set_string("address", db_url)

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
        ok_but = pd.add_button("OK", Gtk.ResponseType.OK)
        cancel_but = pd.add_button("Cancel", Gtk.ResponseType.CANCEL)
        pd.set_transient_for(win)
        pd.set_default_response(Gtk.ResponseType.OK)
        pd_content = pd.get_content_area()

        margin = 5
        need_margins = [pd_content, ok_but, cancel_but]
        for margin_needer in need_margins:
            margin_needer.props.margin_top = margin
            margin_needer.props.margin_bottom = margin
            margin_needer.props.margin_start = margin
            margin_needer.props.margin_end = margin
        # pd_content.props.orientation = Gtk.Orientation.HORIZONTAL

        box_spacing = 5

        outerbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, box_spacing)
        pd_content.append(outerbox)

        urllinebox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, box_spacing)
        lbl = Gtk.Label.new("<b>Datbase connection URL: </b>")
        lbl.props.use_markup = True
        urllinebox.append(lbl)
        server_box = Gtk.Entry.new()
        server_box.set_width_chars(35)
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
            url = self.some_widgets["sbb"].props.text
            self.db_url = self.settings.set_string("address", url)
            self.db_url = url
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
                    vals = [await q.get()]
                GLib.idle_add(self.handle_db_data, vals)

        async def db_listener():
            self.async_loops.append(asyncio.get_running_loop())
            dbw = DBTool(db_uri=self.db_url)
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

    def run(self):
        # parser = argparse.ArgumentParser(description="livechart program")
        # args = parser.parse_args()
        self.app.run()


def main():
    iface = Interface()
    iface.run()


if __name__ == "__main__":
    main()
