# from concurrent.futures import thread
# from email.mime import base
# import queue
import gi

# import pygal
# from pygal.style import LightSolarizedStyle
# from sklearn.feature_selection import SelectFdr

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Rsvg", "2.0")
from gi.repository import GLib, Gtk, Gio, GObject, Adw, Gdk, GdkPixbuf, Rsvg, Pango


from importlib.metadata import version
import collections
import time

from matplotlib import use as mpl_use

mpl_use("module://mplcairo.gtk")
from mplcairo.gtk import FigureCanvas
from matplotlib.text import Annotation as MPLAnnotation

# from matplotlib.backend_bases import FigureCanvasBase
# import matplotlib.pyplot as plt

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
    max_data_length = 1000  # can be None for unbounded
    data = collections.deque([(float("nan"), float("nan"))], max_data_length)
    t0 = 0
    closing = False
    async_loops = []
    threads = []
    channels: list[str] = []  # channels to listen to
    all_channels: list[str] = [""]  # all possible channels
    sparkline_x = 500
    sparkline_y = 50
    channel_widgets = {}  # dict of base widgets, with channel names for keys
    max_plots = 32  # number of plots to retain in the gui
    n_plots = 0  # the number of plots we've currently retained
    h_widgets = []  # container for horizontal box children
    # charts = {}
    # lb = {}  # latest bytes
    # das = {}
    # to_auto_select = ["raw"]  # if a channel name contains any of these strings, auto select it for listening
    to_auto_select = ["event", "raw", "run"]  # if a channel name contains any of these strings, auto select it for listening
    expecting = {}  # construct for holding pending incoming data before it's plotted
    max_expecting = 16  # no more than this many outstanding event ids can be
    known_devices = {}  # construct for holding stuff we know about devices
    db_schema_dot = ""

    def __init__(self):
        self.version = version("livechart")

        app_id = "org.greyltc.livechart"
        self.app = Gtk.Application(application_id=app_id, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.app.connect("activate", self.on_app_activate)
        self.app.connect("shutdown", self.on_app_shutdown)

        self.settings = Gio.Settings.new(app_id)

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

        self.mal = Pango.AttrList.new()
        self.mal.insert(Pango.attr_family_new("monospace"))

        self.ual = Pango.AttrList.new()
        self.ual.insert(Pango.attr_underline_new(Pango.Underline.SINGLE))

        self.bal = Pango.AttrList.new()
        self.bal.insert(Pango.attr_weight_new(Pango.Weight.BOLD))

        # self.chart = pygal.XY(style=LightSolarizedStyle)
        # self.chart.add("", [1, 3, 5, 16, 13, 3, 7, 9, 2, 1, 4, 9, 12, 10, 12, 16, 14, 12, 7, 2])
        # self.chart.add("", [])

    def do_autoselection(self):
        autoselectors = self.to_auto_select
        # autoselectors.append("raw")
        self.channels = []
        for chan in self.all_channels:
            for asel in autoselectors:
                if asel in chan[1]:
                    self.channels.append(chan)

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

            self.db_url = self.settings.get_string("address")

            cbtn = Gtk.Button.new_from_icon_name("call-start")
            cbtn.connect("clicked", self.on_conn_btn_clicked)
            cbtn.props.tooltip_markup = "Connect to backend"
            tb.pack_start(cbtn)

            dbtn = Gtk.Button.new_from_icon_name("call-stop")
            dbtn.connect("clicked", self.on_dsc_btn_clicked)
            dbtn.props.tooltip_markup = "Disconnect from backend"
            tb.pack_start(dbtn)

            # autoscroll switch
            self.asw = Gtk.Switch.new()
            self.asw.props.state = True
            # dbtn.connect("state-set", self.on_switch_change)
            self.asw.props.tooltip_markup = "Turn on to always see the new plot"
            tb.pack_end(self.asw)

            # lbl = Gtk.Label.new("Value=")
            # tb.pack_start(lbl)

            win.props.titlebar = tb

            # help_overlay_builder = Gtk.Builder()
            # if help_overlay_builder.add_from_string(ui_data["help_overlay"]):
            #    help_overlay = help_overlay_builder.get_object("help_overlay")  # Gtk.ShortcutsWindow
            # else:
            #    raise ValueError("Failed to import help overlay UI")

            # collect widgets we'll need to reference later
            # self.some_widgets["val"] = lbl
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
            self.main_box.spacing = 5
            # self.main_box.margin_top = 50
            # self.main_box.margin_bottom = 50
            # self.main_box.margin_start = 50
            # self.main_box.margin_end = 50
            self.main_box.props.vexpand = True
            self.main_box.props.vexpand_set = True

            self.scroller = Gtk.ScrolledWindow.new()
            self.scroller.props.propagate_natural_height = True

            hbox_spacing = 5
            self.hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, hbox_spacing)
            self.hbox.props.margin_top = hbox_spacing
            self.hbox.props.margin_start = hbox_spacing
            self.hbox.props.margin_end = hbox_spacing
            # self.flower = Gtk.FlowBox.new()
            # self.flower.props.max_children_per_line = self.max_plots
            # self.flower.props.min_children_per_line = self.max_plots

            # self.smus_box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 5)
            # self.smus_box.spacing = 5
            # self.smus_box.props.margin_top = 5
            # self.smus_box.props.margin_start = 5
            # self.smus_box.props.margin_end = 5
            # self.smus_box.props.margin_bottom = 5
            # self.main_box.append(self.smus_box)

            self.scroller.set_child(self.hbox)
            self.main_box.append(self.scroller)

            # sep = Gtk.Seperator.new(Gtk.Orientation.HORIZONTAL)
            self.main_box.append(Gtk.Separator.new(Gtk.Orientation.HORIZONTAL))
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

            self.fetch_channels()
            self.do_autoselection()

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
                toast_text = f"Closing connection because of data reception failure: {repr(e)}"
                toast = Adw.Toast.new(toast_text)
                toast.props.timeout = 3
                self.tol.add_toast(toast)
                self.close_conn()
                # self.new_plot()
                # self.canvas.queue_draw()

    def handle_new_raw_data(self, user_data):
        value = user_data[0]

        # widgets
        base = user_data[1][0]
        vl = user_data[1][1]  # voltage label
        vlv = user_data[1][3]  # voltage level bar
        il = user_data[1][2]  # current label
        ilv = user_data[1][4]  # current level bar

        vl.props.label = f"V: {value['v']*1000:+7.1f} [mV]"
        offsettedv = value["v"] - vlv.offset
        if offsettedv < 0:
            vlv.offset = value["v"]
            offsettedv = 0
        elif offsettedv > vlv.props.max_value:
            vlv.props.max_value = offsettedv
        vlv.props.value = offsettedv

        il.props.label = f"I: {value['i']*1000:+7.1f} [mA]"
        offsettedi = value["i"] - ilv.offset
        if offsettedi < 0:
            ilv.offset = value["i"]
            offsettedi = 0
        elif offsettedi > ilv.props.max_value:
            ilv.props.max_value = offsettedi
        ilv.props.value = offsettedi

        # meme = base_widget.props.child
        # meme = base_widget.get_last_child()
        # meme.props.label = "nanoo"

        # vlab = base_widget.get_last_child().get_first_child()
        # ilab = base_widget.get_last_child().get_last_child()
        # vlab.props.label = f"V: {value['v']:+03.6f}V"
        # ilab.props.label = f"I: {value['i']*1000:+03.6f}mA"

        # base_widget.props.child = Gtk.Label.new(f"Voltage={value['v']}V")
        # base_widget.get_child().label = f"Voltage={value['v']}V"
        # base_widget.props.child.label = f"Voltage={value['v']}V"
        # base_widget.props.child.show()
        # base_widget.get_child().queue_draw()

    def handle_db_data(self, vals):
        for v in vals:
            this_chan = v["channel"]
            if "raw" in this_chan:
                if v["eid"] in self.expecting:
                    self.expecting[v["eid"]]["data"].append((v["v"], v["i"], v["t"], v["s"]))
                # if this_chan not in self.channel_widgets:
                #     # make the new widget in the holding box in the correct order
                #     base = Gtk.Frame.new(f"SMU {this_chan.split('_s')[-1]}")  # new base widget
                #     sbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)

                #     svl = Gtk.Label.new()
                #     svl.props.attributes = self.mal
                #     sbox.append(svl)
                #     svlv = Gtk.LevelBar.new()
                #     svlv.offset = v["v"]
                #     svlv.props.max_value = v["v"] - svlv.offset
                #     sbox.append(svlv)

                #     sil = Gtk.Label.new()
                #     sil.props.attributes = self.mal
                #     sbox.append(sil)
                #     silv = Gtk.LevelBar.new()
                #     silv.offset = v["i"]
                #     silv.props.max_value = v["i"] - silv.offset
                #     sbox.append(silv)

                #     base.props.child = sbox
                #     self.channel_widgets[this_chan] = (base, svl, sil, svlv, silv)
                #     if len(self.channel_widgets) > 1:
                #         # (re)sort the dict
                #         self.channel_widgets = dict(sorted(self.channel_widgets.items(), key=lambda x: x[0]))
                #     sorted_channels = list(self.channel_widgets.keys())
                #     this_chan_num = sorted_channels.index(this_chan)
                #     self.smus_box.prepend(base)
                #     if this_chan_num != 0:  # it's not the first one
                #         prev_chan = sorted_channels[this_chan_num - 1]
                #         self.smus_box.reorder_child_after(self.channel_widgets[prev_chan][0], base)

                #     # reset all the numbers on the frame labels
                #     for chan_name, chan_ws in self.channel_widgets.items():
                #         chan_num = sorted_channels.index(chan_name)
                #         chan_frame = chan_ws[0]
                #         chan_frame.props.label = f"SMU{chan_num:03d}"

                # if new_chan:
                #    nsl = Gtk.Label.new("Voltage=")
                # nda = Gtk.DrawingArea.new()
                # nda.props.height_request = self.sparkline_y + 10
                # nda.props.vexpand = True
                # nda.props.vexpand_set = True
                # nda.set_draw_func(self.draw_canvas, len(self.raw_channels) - 1)
                # self.canvas.set_draw_func(self.draw_canvas, len(self.raw_channels) - 1)

                #        self.smus_box.prepend(nsl)
                # if i not in self.charts:
                #    self.charts[i] = pygal.XY(style=LightSolarizedStyle)
                #    self.charts[i].add("", [])

                # self.data.appendleft((v["t"], v["i"] * v["v"]))
                # self.data.appendleft((v["t"], v["v"]))

                ##GLib.idle_add(self.handle_new_raw_data, (v, self.channel_widgets[this_chan]))

                # newt = v["t"]
                # chart_data = self.charts[i].raw_series[0][0]
                # if len(chart_data) >= self.max_data_length:
                #    chart_data.pop(0)
                # chart_data.append((newt, newv))
                # self.update_val(v["v"], i)
                # store latest chart bytes
                # self.lb[i] = GLib.Bytes.new_take(self.charts[i].render_sparkline(width=self.sparkline_x, height=self.sparkline_y, show_dots=False, show_y_labels=True))

                # self.das[i].queue_draw()
                # self.canvas.queue_draw()
                # for k, c in enumerate(self.main_box):
                #    if k == i:
                #        c.queue_draw()
                #        break

            # elif "runs" in this_chan:
            #    new_rid = v["id"]
            #    if new_rid not in self.known_runs:
            #        self.known_runs[new_rid] = fetch_dev_deets
            #    run_msg = f"New Run by {v['user_id']}: {v['name']}"
            #    toast = Adw.Toast.new(run_msg)
            #    toast.props.timeout = 1
            #    self.tol.add_toast(toast)
            #    print(f"new run: ")
            elif "events" in this_chan:
                eid = v["id"]
                did = v["device_id"]
                rid = v["run_id"]
                # if we've never seen this device before, fetch all of them for the run and add them to our known devices
                if did not in self.known_devices:
                    self.fetch_dev_deets(rid)

                # this device
                td = self.known_devices[str(did)]

                # figure out what we should call it in the UI
                dnl = []
                if td["user_label"]:
                    dnl.append(td["user_label"])
                dnl.append(f'{td["slot"]}#{td["pad"]}')
                dev_name = ", ".join(dnl)

                if "tbl_sweep_events" in this_chan:
                    thing = "J-V sweep"
                elif "tbl_ss_events" in this_chan:
                    thing = "Steady State"
                elif "tbl_mppt_events" in this_chan:
                    thing = "Max power point track"
                else:
                    thing = "Unknown"

                if not v["complete"]:
                    what = "started."
                    if thing != "Unknown":
                        if self.n_plots >= self.max_plots:
                            to_remove = self.h_widgets.pop(0)  # remove from the front
                            self.hbox.remove(to_remove)
                            self.n_plots -= 1
                        self.n_plots += 1
                        height = 250  # in pixels on the gui
                        figsize = (6.4, 4.8)  # inches for matplotlib
                        fig = Figure(figsize=figsize, dpi=100, layout="constrained")
                        ax = fig.add_subplot()

                        if "tbl_sweep_events" in this_chan:
                            title = f"J-V: {dev_name}"
                            xlab = "Voltage [V]"
                            ylab = r"Current Density [$\mathregular{\frac{mA}{cm^2}}$]"
                            ax.axhline(0, color="black")
                            ax.axvline(0, color="black")
                            bounds = [v["from_setpoint"], v["to_setpoint"]]
                            left_v = min(bounds)
                            right_v = max(bounds)
                            lns = ax.plot([left_v, right_v], [0, 0], marker="o", linestyle="solid", linewidth=1, markersize=2, markerfacecolor=(1, 1, 0, 0.5))
                        elif "tbl_mppt_events" in this_chan:
                            title = f"MPPT: {dev_name}"
                            xlab = "Time [s]"
                            ylab = r"Power Density [$\mathregular{\frac{mW}{cm^2}}$]"
                            lns = ax.plot([], marker="o", linestyle="solid", linewidth=1, markersize=2, markerfacecolor=(1, 1, 0, 0.5))
                        elif "tbl_ss_events" in this_chan:
                            title = f"{thing}: {dev_name}"
                            xlab = "Time [s]"
                            lns = ax.plot([], marker="o", linestyle="solid", linewidth=1, markersize=2, markerfacecolor=(1, 1, 0, 0.5))
                            if v["fixed"] == 1:
                                ylab = "Voltage [mV]"
                                ax.legend((f'Current Fixed @ {v["setpoint"]}[mA]',))
                            else:
                                ylab = r"Current Density [$\mathregular{\frac{mA}{cm^2}}$]"
                                ax.legend((f'Voltage Fixed @ {v["setpoint"]}[V]',))
                        else:
                            title = "Unknown"
                            xlab = ""
                            ylab = ""
                            lns = ax.plot([], marker="o", linestyle="solid", linewidth=1, markersize=2, markerfacecolor=(1, 1, 0, 0.5))

                        ax.annotate("Collecting Data...", xy=(0.5, 0.5), xycoords="axes fraction", va="center", ha="center", bbox=dict(boxstyle="round", fc="w"))
                        ax.set_title(title)
                        ax.set_xlabel(xlab)
                        ax.set_ylabel(ylab)
                        ax.grid(True)

                        w = FigureCanvas(fig)
                        w.props.content_width = int(height * (figsize[0] / figsize[1]))
                        w.props.content_height = height
                        # w.props.height_request = -1
                        # w.props.width_request = -1
                        w.props.vexpand = False
                        w.props.hexpand = False

                        self.hbox.append(w)
                        self.h_widgets.append(w)

                        # self.hbox.prepend(w)
                        # self.h_widgets.insert(0, w)

                        new_one = {"widget": w, "fig": fig, "lns": lns, "ax": ax, "did": did, "data": []}
                        self.expecting[eid] = new_one
                        if self.asw.props.state:  # if the autoscroll switch is on, scroll all the way to the right
                            GLib.idle_add(self.maxscroll)
                else:  # complete
                    what = "done."
                    expdict = self.expecting.pop(eid, None)
                    if expdict:
                        what = f'complete with {len(expdict["data"])} points.'
                        lns = expdict["lns"]
                        if "tbl_sweep_events" in this_chan:
                            if v["light"]:
                                this_area = self.known_devices[str(did)]["area"]  # in cm^2
                            else:
                                this_area = self.known_devices[str(did)]["dark_area"]  # in cm^2
                            lns[0].set_xdata([x[0] for x in expdict["data"]])
                            lns[0].set_ydata([x[1] * 1000 / this_area for x in expdict["data"]])
                        elif "tbl_mppt_events" in this_chan:
                            area = self.known_devices[str(did)]["area"]  # in cm^2
                            lns[0].set_xdata([x[2] for x in expdict["data"]])
                            lns[0].set_ydata([x[0] * x[1] * -1 * 1000 / area for x in expdict["data"]])
                        elif "tbl_ss_events" in this_chan:
                            area = self.known_devices[str(did)]["area"]  # in cm^2
                            if v["fixed"] == 1:
                                lns[0].set_xdata([x[2] for x in expdict["data"]])
                                lns[0].set_ydata([x[0] * 1000 for x in expdict["data"]])
                            else:
                                lns[0].set_xdata([x[2] for x in expdict["data"]])
                                lns[0].set_ydata([x[1] * 1000 / area for x in expdict["data"]])
                        ax = expdict["ax"]
                        [child.remove() for child in ax.get_children() if isinstance(child, MPLAnnotation)]  # delete annotations
                        ax.relim()
                        ax.autoscale()
                        expdict["fig"].canvas.draw_idle()
                msg = f"{thing} for ({dev_name}) {what}"
                toast = Adw.Toast.new(msg)
                toast.props.timeout = 1
                self.tol.add_toast(toast)

        if len(self.expecting) > 10:
            msg = "You're expecting too much!"
            toast = Adw.Toast.new(msg)
            toast.props.timeout = 1
            self.tol.add_toast(toast)
            self.expecting = {}

        # self.update_val(v["v"], i)
        # self.new_plot()
        # chart_bytes = self.charts[i].render_sparkline(width=self.sparkline_x, height=self.sparkline_y, show_dots=False, show_y_labels=True)
        # self.pbls[0].write_bytes(GLib.Bytes.new_take(chart_bytes))
        # self.pbls[0].close()

    # def on_draw(self, canvas, ctx, xdim, ydim, ud):
    # canvas.draw()
    # ud[0].canvas.draw_idle()

    def maxscroll(self):
        """move the scroll bar all the way to the right"""
        cv = self.scroller.props.hadjustment.props.value  # check where we are now
        mv = self.scroller.props.hadjustment.props.upper  # check the max value
        if cv != mv:  # only scroll if we need to
            self.scroller.props.hadjustment.props.value = mv

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

    def fetch_channels(self, button: Gtk.Button = None, listbox: Gtk.ListBox = None):
        """ask the database for all channel names, updates the channel listbox if it's given"""
        query = "select event_object_schema, event_object_table from information_schema.triggers where event_manipulation = 'INSERT'"
        self.all_channels = []
        self.channels = []
        try:
            with psycopg.connect(self.db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query)
                    for record in cur:
                        if len(record) == 2:
                            self.all_channels.append(record)
                            # self.all_channels.append(f"{record[0]}_{record[1]}")
        except Exception as e:
            print(f"Failure fething channel list from the DB: {e}")

        if len(self.all_channels) == 0:
            self.all_channels = [""]

        if listbox is not None:
            self.update_channel_list(listbox)

        # else:
        #    if fetched_channels != []:
        #        self.all_channels = fetched_channels
        #        self.update_channel_list()

    def fetch_dev_deets(self, rid: int):
        """updates known devices given a run id"""
        query1 = f"""
        select
            trd.device_id,
            tss.name slot,
            ts.name user_label,
            tld.pad_no,
            area(light_cir) area,
            area(dark_cir) dark_area
        from
            {self.db_schema_dot}tbl_run_devices trd
        join {self.db_schema_dot}tbl_devices on
            tbl_devices.id = device_id
        join {self.db_schema_dot}tbl_substrates ts on
            ts.id = substrate_id
        join {self.db_schema_dot}tbl_slot_substrate_run_mappings tssrm on
            tssrm.substrate_id = ts.id
        join {self.db_schema_dot}tbl_layout_devices tld on
            tld.id = layout_device_id
        join {self.db_schema_dot}tbl_setup_slots tss on
            tss.id = slot_id
        where
            trd.run_id = {rid}
        """
        try:
            with psycopg.connect(self.db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query1)
                    for record in cur:
                        id = record[0]
                        rcd = {
                            "slot": record[1],
                            "user_label": record[2],
                            "pad": record[3],
                            "area": record[4],
                            "dark_area": record[5],
                        }
                        self.known_devices[str(id)] = rcd
        except Exception as e:
            print(f"Failure fething device details from the DB: {e}")

    def update_channel_list(self, listbox):
        # clear the list
        while True:
            try:
                listbox.remove(listbox.get_first_child())
            except:
                break

        for chan in self.all_channels:
            row_label = Gtk.Label.new()
            row_label.props.attributes = self.mal
            row_label.set_text(chan[1])
            chan_row = Gtk.ListBoxRow()
            chan_row.props.activatable = False
            chan_row.props.child = row_label
            listbox.append(chan_row)
            if chan in self.channels:
                listbox.select_row(chan_row)

    def url_change(self, *args, **kwargs):
        """handle change in the url string"""
        entry_widget = args[0]
        self.db_url = entry_widget.get_text()

    def on_preferences_action(self, widget, _):
        win = self.app.props.active_window
        # setup prefs dialog
        pd = Gtk.Dialog.new()
        pd.props.resizable = False
        pd.props.title = "Preferences"
        ok_but = pd.add_button("OK", Gtk.ResponseType.OK)
        cancel_but = pd.add_button("Cancel", Gtk.ResponseType.CANCEL)
        pd.set_transient_for(win)
        pd.set_default_response(Gtk.ResponseType.OK)
        content_box = pd.get_content_area()
        content_box.props.orientation = Gtk.Orientation.VERTICAL
        content_box.props.spacing = 5
        content_box.props.margin_top = 5
        content_box.props.margin_start = 5
        content_box.props.margin_end = 5

        margin = 5
        need_margins = [ok_but, cancel_but]
        for margin_needer in need_margins:
            margin_needer.props.margin_top = margin
            margin_needer.props.margin_bottom = margin
            margin_needer.props.margin_start = margin
            margin_needer.props.margin_end = margin
        # pd_content.props.orientation = Gtk.Orientation.HORIZONTAL

        box_spacing = 5

        # outerbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, box_spacing)
        # outerbox.set_hexpand(True)
        # outerbox.compute_expand(Gtk.Orientation.HORIZONTAL)
        # outerbox.set_size_request(-1, -1)
        # outerbox.set_hexpand_set(True)
        # pd_content.append(outerbox)
        sbf = Gtk.Frame.new()
        sbfl = Gtk.Label.new()
        # sbfl.props.attributes = self.ual
        sbfl.props.label = "Datbase Connection URL"
        sbf.props.label_widget = sbfl

        # urllinebox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, box_spacing)
        # urllinebox.set_hexpand(True)
        # urllinebox.set_size_request(-1, -1)
        # urllinebox.compute_expand(Gtk.Orientation.HORIZONTAL)
        # urllinebox.set_hexpand_set(True)
        # lbl = Gtk.Label.new("<b>Datbase connection URL: </b>")
        # lbl.props.use_markup = True
        # urllinebox.append(lbl)
        server_entry = Gtk.Entry.new()
        # al.insert(Pango.AttrWeight(Pango.Weight.BOLD, 0, 50))
        # al.insert(Pango.attr_underline_new(Pango.Underline.SINGLE))
        server_entry.props.attributes = self.mal
        server_entry.props.text = self.db_url
        # server_box.set_max_length(0)
        # server_box.set_size_request(-1, -1)
        # server_box.props.width_chars = len(self.db_url)
        server_entry.props.width_chars = server_entry.props.text_length
        # server_box.set_hexpand(True)
        #
        # server_box.compute_expand(Gtk.Orientation.HORIZONTAL)
        # server_box.set_hexpand_set(True)
        server_entry.connect("changed", self.url_change)
        server_entry.props.placeholder_text = "postgresql://"
        # server_box.props.activates_default = True

        server_entry.props.margin_start = 5
        server_entry.props.margin_end = 5
        server_entry.props.margin_bottom = 5
        sbf.props.child = server_entry
        # urllinebox.append(sbf)
        content_box.append(sbf)

        lf = Gtk.Frame.new()
        lfl = Gtk.Label.new()
        # lfl.props.attributes = self.bal
        lfl.props.label = "Channels to Listen On"
        lf.props.label_widget = lfl
        lb = Gtk.Box.new(Gtk.Orientation.VERTICAL, box_spacing)

        # chanlinebox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, box_spacing)
        # chan_lbl = Gtk.Label.new("<b>Select Listen Channels: </b>")
        # chan_lbl.props.use_markup = True
        # chanlinebox.append(chan_lbl)
        channel_listbox = Gtk.ListBox.new()
        channel_listbox.props.selection_mode = Gtk.SelectionMode.MULTIPLE
        # self.channel_list.props.hexpand = True
        channel_listbox.props.show_separators = True
        channel_listbox.props.activate_on_single_click = False
        self.update_channel_list(channel_listbox)
        lb.append(channel_listbox)

        lcb = Gtk.Button.new_with_label("Refresh")
        lcb.connect("clicked", self.fetch_channels, channel_listbox)
        lb.append(lcb)

        lb.props.margin_start = 5
        lb.props.margin_end = 5
        lb.props.margin_bottom = 5
        lf.props.child = lb
        content_box.append(lf)

        pd.connect("response", self.on_prefs_response, channel_listbox)
        pd.present()

    def on_prefs_response(self, prefs_dialog, response_code, listbox):
        if response_code == Gtk.ResponseType.OK:
            self.settings.set_string("address", self.db_url)
            self.channels = []

            def fill_channels(box: Gtk.ListBox, row: Gtk.ListBoxRow):
                self.channels.append(self.all_channels[row.get_index()])
                # self.channels.append(row.props.child.props.label)

            listbox.selected_foreach(fill_channels)
        else:
            self.db_url = self.settings.get_string("address")
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
            dbw.listen_channels = [f"{chan[0]}_{chan[1]}" for chan in self.channels]
            schemas = set([chan[0] for chan in self.channels])
            if len(schemas) > 1:
                toast_text = "LIstening on multiple schemas.\nThis will not go well..."
                toast = Adw.Toast.new(toast_text)
                toast.props.timeout = 3
                self.tol.add_toast(toast)
            self.db_schema_dot = f"{schemas.pop()}."
            aconn = None
            try:
                aconn = await asyncio.create_task(psycopg.AsyncConnection.connect(conninfo=dbw.db_uri, autocommit=True), name="connect")
                await aconn.set_read_only(True)
                toast_text = f"Connected to {dbw.db_uri}"
            except Exception as e:
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


class BlitManager:
    def __init__(self, canvas, animated_artists=()):
        """
        Parameters
        ----------
        canvas : FigureCanvasAgg
            The canvas to work with, this only works for sub-classes of the Agg
            canvas which have the `~FigureCanvasAgg.copy_from_bbox` and
            `~FigureCanvasAgg.restore_region` methods.

        animated_artists : Iterable[Artist]
            List of the artists to manage
        """
        self.canvas = canvas
        self._bg = None
        self._artists = []

        for a in animated_artists:
            self.add_artist(a)
        # grab the background on every draw
        self.cid = canvas.mpl_connect("draw_event", self.on_draw)

    def on_draw(self, event):
        """Callback to register with 'draw_event'."""
        cv = self.canvas
        if event is not None:
            if event.canvas != cv:
                raise RuntimeError
        self._bg = cv.copy_from_bbox(cv.figure.bbox)
        self._draw_animated()

    def add_artist(self, art):
        """
        Add an artist to be managed.

        Parameters
        ----------
        art : Artist

            The artist to be added.  Will be set to 'animated' (just
            to be safe).  *art* must be in the figure associated with
            the canvas this class is managing.

        """
        if art.figure != self.canvas.figure:
            raise RuntimeError
        art.set_animated(True)
        self._artists.append(art)

    def _draw_animated(self):
        """Draw all of the animated artists."""
        fig = self.canvas.figure
        for a in self._artists:
            fig.draw_artist(a)

    def update(self):
        """Update the screen with animated artists."""
        cv = self.canvas
        fig = cv.figure
        # paranoia in case we missed the draw event,
        if self._bg is None:
            self.on_draw(None)
        else:
            # restore the background
            cv.restore_region(self._bg)
            # draw all of the animated artists
            self._draw_animated()
            # update the GUI state
            cv.blit(fig.bbox)
        # let the GUI event loop process anything it has to do
        cv.flush_events()


def main():
    iface = Interface()
    iface.run()


if __name__ == "__main__":
    main()
