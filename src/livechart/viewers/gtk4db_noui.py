import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Gio, GObject, Adw, Gdk, GdkPixbuf, Pango

from typing import Generator

import livechart

# import pygal
# from pygal.style import LightSolarizedStyle
# from sklearn.feature_selection import SelectFdr


import collections
import time

from matplotlib import use as mpl_use

mpl_use("module://mplcairo.gtk")
from mplcairo.gtk import FigureCanvas
from matplotlib.text import Annotation as MPLAnnotation
from mpl_toolkits.axisartist.parasite_axes import HostAxes, ParasiteAxes

# from matplotlib.backend_bases import FigureCanvasBase
# import matplotlib.pyplot as plt

from matplotlib.figure import Figure

import struct

from livechart.db import DBTool
import psycopg
import asyncio
import threading


class APlot(GObject.Object):
    """plot class"""

    __gtype_name__ = "APlot"
    fig: Figure | None = None
    px_height: float = 250
    px_width: float = 0

    def __init__(self, event_line: dict, this_device: dict):
        super().__init__()
        self.this_device = this_device
        # figure out what we should call this device in the ui
        dnl = []
        if this_device["user_label"]:
            dnl.append(this_device["user_label"])
        dnl.append(f'{this_device["slot"]}#{this_device["pad"]}')
        dev_name = ", ".join(dnl)
        self.event_metadata = {}
        self.event_data = {}

        if "tbl_mppt_events" in event_line["channel"]:
            figsize = (12.8, 4.8)  # inches for matplotlib
        else:
            figsize = (6.4, 4.8)  # inches for matplotlib
        ar = figsize[0] / figsize[1]
        self.px_width = ar * self.px_height
        self.fig = Figure(figsize=figsize, dpi=100, layout="constrained")

        if "tbl_mppt_events" in event_line["channel"]:
            ax = []
            ax.append(self.fig.add_axes([0.13, 0.15, 0.65, 0.74], axes_class=HostAxes))
            ax.append(ParasiteAxes(ax[0], sharex=ax[0]))
            ax.append(ParasiteAxes(ax[0], sharex=ax[0]))
            ax[0].parasites.append(ax[1])
            ax[0].parasites.append(ax[2])
            ax[0].axis["right"].set_visible(False)

            ax[1].axis["right"].set_visible(True)
            ax[1].axis["right"].major_ticklabels.set_visible(True)
            ax[1].axis["right"].label.set_visible(True)

            ax[2].axis["right2"] = ax[2].new_fixed_axis(loc="right", offset=(50, 0))

            lns = ax[0].plot([], marker="o", linestyle="solid", linewidth=2, markersize=3, markerfacecolor=(1, 1, 0, 0.5))
            lns += ax[1].plot([], marker="o", linestyle="solid", linewidth=1, markersize=2, alpha=0.2)
            lns += ax[2].plot([], marker="o", linestyle="solid", linewidth=1, markersize=2, alpha=0.2)

            ax[1].set_ylabel("Voltage [mV]")
            ax[2].set_ylabel(r"Current Density [$\mathregular{\frac{mA}{cm^2}}$]")

            ax[0].yaxis.set_major_formatter("{x:.2f}")
            ax[1].yaxis.set_major_formatter("{x:.0f}")
            ax[2].yaxis.set_major_formatter("{x:.1f}")

            ax[0].axis["left"].label.set_color(lns[0].get_color())
            ax[1].axis["right"].label.set_color(lns[1].get_color())
            ax[2].axis["right2"].label.set_color(lns[2].get_color())

            title = f"MPPT: {dev_name}"
            xlab = "Time [s]"
            ylab = r"Power Density [$\mathregular{\frac{mW}{cm^2}}$]"
        elif "tbl_sweep_events" in event_line["channel"]:
            ax = self.fig.add_subplot()
            title = f"J-Vs: {dev_name}"
            xlab = "Voltage [V]"
            ylab = r"Current Density [$\mathregular{\frac{mA}{cm^2}}$]"
            ax.axhline(0, color="black")
            ax.axvline(0, color="black")
            ax.annotate("Collecting Data...", xy=(0.5, 0.5), xycoords="axes fraction", va="center", ha="center", bbox=dict(boxstyle="round", fc="chartreuse"))
            lns = None
        elif "tbl_ss_events" in event_line["channel"]:
            ax = self.fig.add_subplot()
            title = f"Steady State: {dev_name}"
            xlab = "Time [s]"
            if event_line["fixed"] == 1:
                led_txt = f'Current Fixed @ {event_line["setpoint"]}[mA]'
                ylab = "Voltage [mV]"
            else:
                led_txt = f'Voltage Fixed @ {event_line["setpoint"]}[V]'
                ylab = r"Current Density [$\mathregular{\frac{mA}{cm^2}}$]"
            lns = ax.plot([], label=led_txt, marker="o", linestyle="solid", linewidth=1, markersize=2, markerfacecolor=(1, 1, 0, 0.5))
            ax.legend()
        else:
            ax = self.fig.add_subplot()
            title = "Unknown"
            xlab = ""
            ylab = ""
            lns = ax.plot([], marker="o", linestyle="solid", linewidth=1, markersize=2, markerfacecolor=(1, 1, 0, 0.5))

        if isinstance(ax, list):
            # ax[2].annotate("Collecting Data...", xy=(0.5, 0.5), xycoords="axes fraction", va="center", ha="center", bbox=dict(boxstyle="round", fc="chartreuse"))
            ax[0].set_title(title)
            ax[0].set_xlabel(xlab)
            ax[0].set_ylabel(ylab)
            ax[0].grid(True)
        elif ax:
            ax.set_title(title)
            ax.set_xlabel(xlab)
            ax.set_ylabel(ylab)
            ax.grid(True)

        self.register_event(event_line)

    @GObject.Property(type=GObject.TYPE_INT)
    def width_px(self):
        """figure width in pixels"""
        if self.fig:
            ret = self.px_width
            # ret = self.fig.bbox.bounds[2]
        else:
            ret = 0
        return ret

    @GObject.Property(type=GObject.TYPE_INT)
    def height_px(self):
        """figure height in pixels"""
        if self.fig:
            ret = self.px_height
            # ret = self.fig.bbox.bounds[3]
        else:
            ret = 0
        return ret

    def add_data(self, eid, new_data):
        eid_str = str(eid)
        if eid_str in self.event_data:
            self.event_data[eid_str].append(new_data)
        else:
            self.event_data[eid_str] = [new_data]
        event = self.event_metadata[eid_str]
        if self.fig:
            if "mppt" in event["channel"]:
                t0 = self.event_data[eid_str][0][2]
                t = [x[2] - t0 for x in self.event_data[eid_str]]
                axes = self.fig.axes + self.fig.axes[0].parasites

                # power
                nlax = axes[0]
                ln = nlax.get_lines()[0]
                ln.set_xdata(t)
                ln.set_ydata([x[0] * x[1] * -1 * 1000 / self.this_device["area"] for x in self.event_data[eid_str]])

                # voltage
                nlax = axes[1]
                ln = nlax.get_lines()[0]
                ln.set_xdata(t)
                ln.set_ydata([x[0] * 1000 for x in self.event_data[eid_str]])

                # current
                nlax = axes[2]
                ln = nlax.get_lines()[0]
                ln.set_xdata(t)
                ln.set_ydata([x[1] * -1 * 1000 / self.this_device["area"] for x in self.event_data[eid_str]])
            elif "ss" in event["channel"]:
                t0 = self.event_data[eid_str][0][2]
                t = [x[2] - t0 for x in self.event_data[eid_str]]
                axes = self.fig.axes
                ln = axes[0].get_lines()[0]
                ln.set_xdata(t)
                if ln.get_label().startswith("Current"):
                    ln.set_ydata([x[0] * 1000 for x in self.event_data[eid_str]])
                else:
                    ln.set_ydata([x[1] * 1000 / self.this_device["area"] for x in self.event_data[eid_str]])
            else:
                axes = []

            # if self.fig.canvas.get_mapped():
            GLib.idle_add(self.idle_update, axes)

    def register_event(self, event_line):
        self.event_metadata[str(event_line["id"])] = event_line
        eid_str = str(event_line["id"])
        if ("tbl_sweep_events" in event_line["channel"]) and (event_line["complete"]) and (eid_str in self.event_data):
            axes = self.fig.axes
            ax = axes[0]
            [child.remove() for child in ax.get_children() if isinstance(child, MPLAnnotation)]  # delete annotations
            if event_line["light"]:
                lit = "light"
                area = self.this_device["area"]
            else:
                lit = "dark"
                area = self.this_device["dark_area"]
            if event_line["from_setpoint"] < event_line["to_setpoint"]:
                swp_dir = r"$\Longrightarrow$"
            else:
                swp_dir = r"$\Longleftarrow$"
            (line,) = ax.plot(
                [x[0] for x in self.event_data[eid_str]],
                [x[1] * 1000 / area for x in self.event_data[eid_str]],
                label=f"{lit}{swp_dir}",
                marker="o",
                linestyle="solid",
                linewidth=1,
                markersize=2,
                markerfacecolor=(1, 1, 0, 0.5),
            )
            ax.legend()

            # if self.fig.canvas.get_mapped():
            GLib.idle_add(self.idle_update, axes)

    def idle_update(self, iax):
        # prepare the axes and queue up the redraw only if the widget is mapped
        for ax in iax:
            ax.relim()
            ax.autoscale()
        if iax and hasattr(self.fig, "canvas"):
            self.fig.canvas.draw_idle()


class DataRow(GObject.Object):
    """table row class"""

    __gtype_name__ = "DataRow"
    col_defs = [
        # {"name": "user", "title": "User", "width": 120},
        # {"name": "run_id", "title": "Run ID", "width": 80},
        {"name": "run_name", "title": "Run Name", "width": 140},
        {"name": "slot", "title": "Slot", "width": None},
        {"name": "pad", "title": "Pad", "width": None},
        {"name": "user_label", "title": "Label", "width": 120},
        {"name": "area", "title": "Area[cm^2]", "width": None},
        # {"name": "dark_area", "title": "Dark Area[cm^2]", "width": None},
        {"name": "voc_ss", "title": "V_oc[V]", "width": 100},
        {"name": "jsc_ss", "title": "J_sc[mA/cm^2]", "width": None},
        {"name": "pmax_ss", "title": "P_max[mW/cm^2]", "width": None},
    ]

    def __init__(self, **kwargs):
        super().__init__()
        self._row_data = {}
        for col in self.col_defs:
            self._row_data[col["name"]] = ""

        for key, val in kwargs.items():
            if "area" in key:
                val = round(val, 4)
            self._row_data[key] = val

    # TODO: possibly try to use a class factory or something for all these instead of doing them manually
    @GObject.Property(type=str)
    def user_label(self):
        return self._row_data["user_label"]

    @GObject.Property(type=str)
    def slot(self):
        return self._row_data["slot"]

    @GObject.Property(type=str)
    def pad(self):
        return self._row_data["pad"]

    @GObject.Property(type=str)
    def run_id(self):
        return self._row_data["run_id"]

    @GObject.Property(type=str)
    def run_name(self):
        return self._row_data["run_name"]

    @GObject.Property(type=str)
    def area(self):
        return self._row_data["area"]

    @GObject.Property(type=str)
    def dark_area(self):
        return self._row_data["dark_area"]

    @GObject.Property(type=str)
    def voc_ss(self):
        return self._row_data["voc_ss"]

    @GObject.Property(type=str)
    def jsc_ss(self):
        return self._row_data["jsc_ss"]

    @GObject.Property(type=str)
    def pmax_ss(self):
        return self._row_data["pmax_ss"]


class Interface(object):
    app = None
    version = livechart.__version__
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
    max_plots = 64  # number of plots to retain in the gui
    n_plots = 0  # the number of plots we've currently retained
    row_model: Gio.ListStore
    plot_model: Gio.ListStore
    cols = []
    counter = 0
    event_id_to_plot_model_mapping: dict[str, int] = {}  # given an event ID, which plot model index should we use
    device_jv_event_groups = {}  # given a device id, which jv event IDs dies it have?

    # charts = {}
    # lb = {}  # latest bytes
    # das = {}
    # to_auto_select = ["raw"]  # if a channel name contains any of these strings, auto select it for listening
    to_auto_select = ["event", "raw", "run"]  # if a channel name contains any of these strings, auto select it for listening
    max_expecting = 16  # no more than this many outstanding event ids can be
    db_schema_dot = ""
    last_run = None

    def __init__(self):
        self.h_widgets = []  # container for horizontal box children
        self.expecting = {}  # construct for holding pending incoming data before it's plotted
        self.known_devices = {}  # construct for holding stuff we know about devices
        self.did_possibly_mid_series = set()  # device IDs that are possibly mid-sweep series
        self.countsup = Interface.counter_sequence()

        app_id = "org.greyltc.livechart"
        self.app = Gtk.Application(application_id=app_id, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.app.connect("activate", self.on_app_activate)
        self.app.connect("shutdown", self.on_app_shutdown)

        self.settings = Gio.Settings.new(app_id)

        # self.sorter = Gtk.StringSorter.new()
        self.row_model = Gio.ListStore.new(DataRow)
        # self.sorted_row_model = Gtk.SortListModel.new(self.row_model, self.sorter)

        self.plot_model = Gio.ListStore.new(APlot)

        # setup about dialog
        self.ad = Gtk.AboutDialog.new()
        self.ad.props.program_name = "livechart"
        self.ad.props.version = self.version
        self.ad.props.authors = ["Greyson Christoforo"]
        self.ad.props.copyright = "(C) 2022 Grey Christoforo"
        self.ad.props.logo_icon_name = "monitoring-system-icon"

        self.t0 = time.time()
        self.s = Gio.SocketClient.new()
        self.float_size = struct.calcsize("f")

        self.mal = Pango.AttrList.new()
        self.mal.insert(Pango.attr_family_new("monospace"))

        self.ual = Pango.AttrList.new()
        self.ual.insert(Pango.attr_underline_new(Pango.Underline.SINGLE))

        self.bal = Pango.AttrList.new()
        self.bal.insert(Pango.attr_weight_new(Pango.Weight.BOLD))

        self.scroll_start = None

        # self.chart = pygal.XY(style=LightSolarizedStyle)
        # self.chart.add("", [1, 3, 5, 16, 13, 3, 7, 9, 2, 1, 4, 9, 12, 10, 12, 16, 14, 12, 7, 2])
        # self.chart.add("", [])

    def record_start(self, gesture, start_x, start_y):
        self.scroll_start = gesture.get_widget().props.hadjustment.props.value

    def pan_done(self, gesture, start_x, start_y):
        self.scroll_start = None

    def do_pan(self, gesture, direction, distance):
        scroller = gesture.get_widget()
        max_pos = scroller.props.hadjustment.props.upper
        min_pos = scroller.props.hadjustment.props.lower
        if self.scroll_start is not None:
            if direction == Gtk.PanDirection.RIGHT:
                new_pos = self.scroll_start - distance
            else:
                new_pos = self.scroll_start + distance

            if new_pos > max_pos:
                new_pos = max_pos
            elif new_pos < min_pos:
                new_pos = min_pos

            scroller.props.hadjustment.props.value = new_pos

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
            win.props.default_height = 480
            # win.props.default_width = 640
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
            win.props.title = f"livechart"

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

            self.hscroller = Gtk.ScrolledWindow.new()
            self.hscroller.props.propagate_natural_height = True
            # self.hscroller.props.halign = Gtk.Align.END

            # self.hscroller.props.hadjustment.connect("changed", self.scroll_change)

            hfactory = Gtk.SignalListItemFactory.new()
            hfactory.connect("setup", self._on_hfactory_setup)
            hfactory.connect("bind", self._on_hfactory_bind)
            hfactory.connect("unbind", self._on_hfactory_unbind)
            hfactory.connect("teardown", self._on_hfactory_teardown)

            self.panner = Gtk.GesturePan(orientation=Gtk.Orientation.HORIZONTAL, n_points=1)
            # self.panner.connect("pan", self.do_pan)
            self.panner.connect("drag-begin", self.record_start)
            self.panner.connect("drag-end", self.pan_done)

            self.hscroller.add_controller(self.panner)

            # autoscroll switch
            self.asw = Gtk.Switch.new()
            self.asw.props.state = True
            self.asw.connect("state_set", self.scroll_switch_state_change)
            # dbtn.connect("state-set", self.on_switch_change)
            self.asw.props.tooltip_markup = "Turn on to always see the new plot"
            tb.pack_end(self.asw)

            self.scroll_switch_state_change(self.asw, self.asw.props.state)

            self.hlist = Gtk.ListView.new(Gtk.NoSelection.new(self.plot_model), hfactory)
            self.hlist.set_single_click_activate(False)
            self.hlist.props.orientation = Gtk.Orientation.HORIZONTAL
            self.hlist.props.show_separators = True
            self.hlist.props.halign = Gtk.Align.END

            # hbox_spacing = 5
            # self.hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, hbox_spacing)
            # self.hbox.props.margin_top = hbox_spacing
            # self.hbox.props.margin_start = hbox_spacing
            # self.hbox.props.margin_end = hbox_spacing

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

            self.hscroller.set_child(self.hlist)
            self.main_box.append(self.hscroller)

            # sep = Gtk.Seperator.new(Gtk.Orientation.HORIZONTAL)
            self.main_box.append(Gtk.Separator.new(Gtk.Orientation.HORIZONTAL))

            cv = Gtk.ColumnView.new(Gtk.MultiSelection.new(self.row_model))
            # TODO: work out how to sort by clicking
            # cv.props.model = Gtk.MultiSelection.new(Gtk.SortListModel.new(self.row_model, cv.props.sorter))
            cv.props.show_row_separators = True
            cv.props.show_column_separators = True
            cv.props.reorderable = False
            # cv.props.sorter = Gtk.StringSorter.new()
            cv.props.vexpand = True
            cv.props.enable_rubberband = True
            cv.props.halign = Gtk.Align.CENTER

            for col_def in DataRow.col_defs:
                factory = Gtk.SignalListItemFactory.new()
                factory.connect("setup", self._on_factory_setup)
                factory.connect("bind", self._on_factory_bind, col_def["name"])
                factory.connect("unbind", self._on_factory_unbind)
                factory.connect("teardown", self._on_factory_teardown)
                cvc = Gtk.ColumnViewColumn.new(title=col_def["title"], factory=factory)
                if col_def["width"]:
                    cvc.props.fixed_width = col_def["width"]
                else:
                    cvc.props.expand = True
                cvc.props.resizable = True
                # cvc.props.sorter = Gtk.StringSorter.new()
                cv.append_column(cvc)

            sw = Gtk.ScrolledWindow.new()
            # sw.props.height_request = 600
            # sw.props.min_content_width = -1
            # sw.props.max_content_width = -1
            # sw.props.min_content_width = 800
            sw.props.propagate_natural_width = True
            sw.props.child = cv
            self.main_box.append(sw)

            # btn = Gtk.Button.new_with_label("Add Rows")
            # btn.connect("clicked", self.add_rows)
            # self.main_box.prepend(btn)

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

    def scroll_switch_state_change(self, switch, state):
        if state:
            self.hscroller.props.hadjustment.set_value(self.hscroller.props.hadjustment.props.upper - self.hscroller.props.hadjustment.props.page_size)
            try:
                self.panner.disconnect_by_func(self.do_pan)
            except:
                pass  # maybe it was never connected, that's okay
            self.hscroller.props.hadjustment.connect("changed", self.peg_scroller)
            self.hscroller.props.hscrollbar_policy = Gtk.PolicyType.EXTERNAL  # EXTERNAL, NEVER

        else:
            self.panner.connect("pan", self.do_pan)
            self.hscroller.props.hscrollbar_policy = Gtk.PolicyType.AUTOMATIC

            try:
                self.hscroller.props.hadjustment.disconnect_by_func(self.peg_scroller)
            except:
                pass  # maybe it was never connected, that's okay

        # return False

    def peg_scroller(self, hadjustment):
        """pins the scroll bar to the right"""
        scroll_later = lambda hadjustment: hadjustment.set_value(hadjustment.props.upper - hadjustment.props.page_size)
        GLib.idle_add(scroll_later, hadjustment)
        # max = hadjustment.props.upper - hadjustment.props.page_size
        # hadjustment.set_value(max)
        # print(f"loc = {hadjustment.props.value}")
        # print(f"max = {max}")
        # cv = self.hscroller.props.hadjustment.props.value  # check where we are now
        # mv = self.hscroller.props.hadjustment.props.upper  # check the max value
        # if cv != mv:  # only scroll if we need to
        #    self.hscroller.props.hadjustment.props.value = mv

    # def add_rows(self, btn):
    #    n = 10
    #    for i in range(n):
    #        self.row_model.append(DataRow())

    @staticmethod
    def counter_sequence(start: int = 0) -> Generator[int, int | None, None]:
        """infinite upwards integer sequence generator"""
        c = start
        while True:
            yield c
            c += 1

    # def was_mapped(self, *args):
    #     print(f"MAP! {args}")

    # def was_unmapped(self, *args):
    #     print(f"UNMAP! {args}")

    def _on_hfactory_setup(self, factory, list_item):
        list_item.props.activatable = False
        list_item.props.selectable = False
        # pass
        # height = 250  # in pixels on the gui
        # a_plot = list_item.get_item()

        # figsize = (6.4, 4.8)  # inches for matplotlib
        # self.fig = Figure(figsize=figsize, dpi=100, layout="constrained")
        # ax = self.fig.add_subplot()
        # ax.set_title("hello")
        # widget = FigureCanvas(self.fig)
        # plot_widget = Gtk.Label.new("john")
        # plot_widget.content_width = int(height * (figsize[0] / figsize[1]))
        # plot_widget.content_height = height
        # widget.props.height_request = height
        # widget.props.width_request = int(height * (figsize[0] / figsize[1]))
        # plot_widget.vexpand = False
        # plot_widget.hexpand = False
        # self.widget._binding = None

        # list_item.set_child(a_plot.props.plot_widget)
        # canvas = FigureCanvas(Figure(layout="constrained"))
        # canvas._binding = None
        # list_item.set_child(canvas)
        # if self.asw.props.state:
        #    GLib.idle_add(self.minscroll)
        # plot_widget.draw_idle()
        # fig.canvas.draw_idle()

    def _on_hfactory_bind(self, factory, list_item):
        a_plot = list_item.get_item()

        canvas = FigureCanvas(a_plot.fig)
        # canvas.props.content_width = a_plot.fig.bbox.bounds[2]
        # canvas.props.content_height = a_plot.fig.bbox.bounds[3]

        canvas._binding = a_plot.bind_property("width_px", canvas, "content_width", GObject.BindingFlags.SYNC_CREATE)
        canvas._binding = a_plot.bind_property("height_px", canvas, "content_height", GObject.BindingFlags.SYNC_CREATE)
        # canvas.connect("map", self.was_mapped)
        # canvas.connect("unmap", self.was_unmapped)
        list_item.set_child(canvas)

    def _on_hfactory_unbind(self, factory, list_item):
        canvas = list_item.get_child()
        if canvas._binding:
            canvas._binding.unbind()
            # canvas.disconnect("map")
            # canvas.disconnect("unmap")
            canvas._binding = None

    def _on_hfactory_teardown(self, factory, list_item):
        canvas = list_item.get_child()
        if canvas:
            canvas._binding = None

    def _on_factory_setup(self, factory, list_item):
        cell = Gtk.Inscription()
        cell._binding = None
        list_item.set_child(cell)

    def _on_factory_bind(self, factory, list_item, what):
        cell = list_item.get_child()
        data_row = list_item.get_item()
        cell._binding = data_row.bind_property(what, cell, "text", GObject.BindingFlags.SYNC_CREATE)

    def _on_factory_unbind(self, factory, list_item):
        cell = list_item.get_child()
        if cell._binding:
            cell._binding.unbind()
            cell._binding = None

    def _on_factory_teardown(self, factory, list_item):
        cell = list_item.get_child()
        if cell:
            cell._binding = None

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
            raw_dat = False
            event_dat = False
            if "raw" in this_chan:
                raw_dat = True
                eid = v["eid"]
            elif "events" in this_chan:
                event_dat = True
                eid = v["id"]
            else:
                print("Message in unknown channel")
                continue  # bail out if we don't understand the channel

            eid_str = str(eid)
            if eid_str not in self.event_id_to_plot_model_mapping:
                if event_dat:
                    did_str = str(v["device_id"])
                    rid = v["run_id"]
                    if did_str not in self.known_devices:
                        self.fetch_dev_deets(rid)
                    td = self.known_devices[did_str]  # this device
                    if "tbl_sweep_events" in this_chan:
                        did = v["device_id"]
                        did_str = str(did)
                        # handle the case we want to group data from different jvs into the same plot
                        if did_str not in self.device_jv_event_groups:
                            pm = APlot(event_line=v, this_device=td)
                            self.plot_model.append(pm)
                            mod_index = len(self.plot_model) - 1
                            self.event_id_to_plot_model_mapping[eid_str] = mod_index
                            self.device_jv_event_groups[did_str] = (mod_index, [eid])
                        else:
                            self.event_id_to_plot_model_mapping[eid_str] = self.device_jv_event_groups[did_str][0]
                            self.device_jv_event_groups[did_str][1].append(eid)
                            pm = self.plot_model[self.device_jv_event_groups[did_str][0]]
                    else:
                        pm = APlot(event_line=v, this_device=td)
                        self.plot_model.append(pm)
                        mod_index = len(self.plot_model) - 1
                        # self.plot_model.insert(0, a_plot)
                        self.event_id_to_plot_model_mapping[eid_str] = mod_index
                else:
                    continue  # bail out if this is raw data for an event we missed the intro to
            else:
                pm = self.plot_model[self.event_id_to_plot_model_mapping[eid_str]]

            if raw_dat:
                pm.add_data(eid, (v["v"], v["i"], v["t"], v["s"]))
                continue

            if event_dat:
                pm.register_event(v)

    def handle_db_data2(self, vals):
        for v in vals:
            this_chan = v["channel"]
            if "raw" in this_chan:
                eid = v["eid"]
                if str(eid) in self.expecting:
                    expecdict = self.expecting[str(eid)]
                    did = expecdict["did"]
                    td = self.known_devices[str(did)]  # this device
                    area = expecdict["area"]  # in cm^2
                    lns = expecdict["lns"]
                    fig = expecdict["fig"]
                    ax = expecdict["ax"]
                    dline = (v["v"], v["i"], v["t"], v["s"])  # new data line
                    expecdict["data"].append(dline)

                    if "mppt" in this_chan:
                        # update the plot data
                        t0 = expecdict["data"][0][2]
                        t = [x[2] - t0 for x in expecdict["data"]]

                        # power
                        lns[0].set_xdata(t)
                        lns[0].set_ydata([x[0] * x[1] * -1 * 1000 / area for x in expecdict["data"]])

                        # voltage
                        lns[1].set_xdata(t)
                        lns[1].set_ydata([x[0] for x in expecdict["data"]])

                        # current
                        lns[2].set_xdata(t)
                        lns[2].set_ydata([x[1] * -1 * 1000 / area for x in expecdict["data"]])

                        # prepare the axes and queue up the redraw
                        for axnx in ax:
                            axnx.relim()
                            axnx.autoscale()
                        # fig.canvas.draw_idle()
                    elif "ss" in this_chan:
                        t0 = expecdict["data"][0][2]
                        t = [x[2] - t0 for x in expecdict["data"]]
                        # update the plot data
                        if lns[0].get_label().startswith("Current"):
                            lns[0].set_xdata(t)
                            lns[0].set_ydata([x[0] * 1000 for x in expecdict["data"]])
                        else:
                            lns[0].set_xdata(t)
                            lns[0].set_ydata([x[1] * 1000 / area for x in expecdict["data"]])

                        # prepare the axes and queue up the redraw
                        ax.relim()
                        ax.autoscale()
                        # fig.canvas.draw_idle()
            elif "events" in this_chan:
                eid = v["id"]
                did = v["device_id"]
                rid = v["run_id"]

                # if it's a new run, let's freshen some stuff
                # TODO: figure out why this isn't cleaning things up properly
                # if self.last_run and (rid != self.last_run):
                #    self.last_run = rid
                #    del self.did_possibly_mid_series
                #    del self.expecting
                #    del self.known_devices
                #    for h_widget in self.h_widgets:
                #        self.hbox.remove(h_widget)
                #    del self.h_widgets
                #    gc.collect()
                #    self.expecting = {}
                #    self.known_devices = {}
                #    self.h_widgets = []
                #    self.did_possibly_mid_series = set()

                # if we've never seen this device before, fetch all of them for the run and add them to our known devices
                if str(did) not in self.known_devices:
                    self.fetch_dev_deets(rid)

                td = self.known_devices[str(did)]  # this device

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
                            # self.hbox.remove(to_remove)
                            self.n_plots -= 1
                        self.n_plots += 1
                        height = 250  # in pixels on the gui
                        if "tbl_mppt_events" in this_chan:
                            figsize = (12.8, 4.8)  # inches for matplotlib
                        else:
                            figsize = (6.4, 4.8)  # inches for matplotlib
                        fig = Figure(figsize=figsize, dpi=100, layout="constrained")

                        new_plot = True
                        if "tbl_sweep_events" in this_chan:
                            self.did_possibly_mid_series.add(did)  # this device might be mid-sweep serties

                            # search for another event to plot into
                            for val in self.expecting.values():
                                if did == val["did"]:
                                    new_ax = val["ax"]
                                    if (hasattr(new_ax, "title")) and ("J-V" in str(new_ax.title)):
                                        new_plot = False
                                        break
                            if new_plot:
                                a_plot = APlot(channel=this_chan, title="e")
                                # self.plot_model.append(a_plot)
                                self.plot_model.insert(0, a_plot)
                                ax = fig.add_subplot()
                                title = f"J-Vs: {dev_name}"
                                xlab = "Voltage [V]"
                                ylab = r"Current Density [$\mathregular{\frac{mA}{cm^2}}$]"
                                ax.axhline(0, color="black")
                                ax.axvline(0, color="black")
                                ax.annotate("Collecting Data...", xy=(0.5, 0.5), xycoords="axes fraction", va="center", ha="center", bbox=dict(boxstyle="round", fc="chartreuse"))
                            else:
                                ax = None
                                title = ""
                                xlab = ""
                                ylab = ""
                            lns = None
                        elif "tbl_mppt_events" in this_chan:
                            self.did_possibly_mid_series.discard(did)  # this device is definitely not mid-sweep series
                            ax = []
                            ax.append(fig.add_axes([0.13, 0.15, 0.65, 0.74], axes_class=HostAxes))
                            ax.append(ParasiteAxes(ax[0], sharex=ax[0]))
                            ax.append(ParasiteAxes(ax[0], sharex=ax[0]))
                            ax[0].parasites.append(ax[1])
                            ax[0].parasites.append(ax[2])
                            ax[0].axis["right"].set_visible(False)

                            ax[1].axis["right"].set_visible(True)
                            ax[1].axis["right"].major_ticklabels.set_visible(True)
                            ax[1].axis["right"].label.set_visible(True)

                            ax[2].axis["right2"] = ax[2].new_fixed_axis(loc="right", offset=(50, 0))

                            lns = ax[0].plot([], marker="o", linestyle="solid", linewidth=2, markersize=3, markerfacecolor=(1, 1, 0, 0.5))
                            lns += ax[1].plot([], marker="o", linestyle="solid", linewidth=1, markersize=2, alpha=0.2)
                            lns += ax[2].plot([], marker="o", linestyle="solid", linewidth=1, markersize=2, alpha=0.2)

                            ax[1].set_ylabel("Voltage [V]")
                            ax[2].set_ylabel(r"Current Density [$\mathregular{\frac{mA}{cm^2}}$]")

                            # ax.legend()

                            ax[0].axis["left"].label.set_color(lns[0].get_color())
                            ax[1].axis["right"].label.set_color(lns[1].get_color())
                            ax[2].axis["right2"].label.set_color(lns[2].get_color())

                            title = f"MPPT: {dev_name}"
                            xlab = "Time [s]"
                            ylab = r"Power Density [$\mathregular{\frac{mW}{cm^2}}$]"
                        elif "tbl_ss_events" in this_chan:
                            self.did_possibly_mid_series.discard(did)  # this device is definitely not mid-sweep series
                            ax = fig.add_subplot()
                            title = f"{thing}: {dev_name}"
                            xlab = "Time [s]"

                            if v["fixed"] == 1:
                                led_txt = f'Current Fixed @ {v["setpoint"]}[mA]'
                                ylab = "Voltage [mV]"
                            else:
                                ylab = r"Current Density [$\mathregular{\frac{mA}{cm^2}}$]"
                                led_txt = f'Voltage Fixed @ {v["setpoint"]}[V]'
                            lns = ax.plot([], label=led_txt, marker="o", linestyle="solid", linewidth=1, markersize=2, markerfacecolor=(1, 1, 0, 0.5))
                            ax.legend()
                        else:
                            self.did_possibly_mid_series.discard(did)  # this device is definitely not mid-sweep series
                            ax = fig.add_subplot()
                            title = "Unknown"
                            xlab = ""
                            ylab = ""
                            lns = ax.plot([], marker="o", linestyle="solid", linewidth=1, markersize=2, markerfacecolor=(1, 1, 0, 0.5))

                        if isinstance(ax, list):
                            # ax[2].annotate("Collecting Data...", xy=(0.5, 0.5), xycoords="axes fraction", va="center", ha="center", bbox=dict(boxstyle="round", fc="chartreuse"))
                            ax[0].set_title(title)
                            ax[0].set_xlabel(xlab)
                            ax[0].set_ylabel(ylab)
                            ax[0].grid(True)
                        elif ax:
                            ax.set_title(title)
                            ax.set_xlabel(xlab)
                            ax.set_ylabel(ylab)
                            ax.grid(True)

                        # if new_plot:
                        # pass
                        # w = FigureCanvas(fig)
                        # w.props.content_width = int(height * (figsize[0] / figsize[1]))
                        # w.props.content_height = height
                        # w.props.height_request = -1
                        # w.props.width_request = -1
                        # w.props.vexpand = False
                        # w.props.hexpand = False

                        # self.hbox.append(w)
                        # self.h_widgets.append(w)
                        # a_plot = APlot()
                        # self.plot_model.append(a_plot)
                        # self.plot_model.insert(0, a_plot)

                        # if self.asw.props.state:  # if the autoscroll switch is on, scroll all the way to the right
                        #    GLib.idle_add(self.minscroll)
                        #    GLib.idle_add(self.maxscroll)
                        # else:  # we're skipping making a new plot for this one
                        #    w = None

                        # self.hbox.prepend(w)
                        # self.h_widgets.insert(0, w)

                        new_one = {"widget": None, "fig": fig, "lns": lns, "ax": ax, "did": did, "area": v["effective_area"], "data": []}
                        self.expecting[str(eid)] = new_one  # register a new expecdict to catch data we get for it
                else:  # complete
                    what = "done."
                    if str(eid) in self.expecting:
                        expecdict = self.expecting[str(eid)]
                        if expecdict["data"]:
                            data = expecdict["data"]
                            area = expecdict["area"]  # in cm^2
                            what = f"complete with {len(data)} points."

                            # search for a pre-existing sweep event for the same device to plot into
                            for val in self.expecting.values():
                                if did == val["did"]:
                                    new_ax = val["ax"]
                                    if (hasattr(new_ax, "title")) and ("J-V" in str(new_ax.title)):
                                        expecdict = val
                                        break

                            lns = expecdict["lns"]
                            ax = expecdict["ax"]
                            fig = expecdict["fig"]
                            if "tbl_sweep_events" in this_chan:
                                if v["light"]:
                                    lit = "light"
                                else:
                                    lit = "dark"
                                if v["from_setpoint"] < v["to_setpoint"]:
                                    swp_dir = r"$\Longrightarrow$"
                                else:
                                    swp_dir = r"$\Longleftarrow$"
                                (line,) = ax.plot(
                                    [x[0] for x in data],
                                    [x[1] * 1000 / area for x in data],
                                    label=f"{lit}{swp_dir}",
                                    marker="o",
                                    linestyle="solid",
                                    linewidth=1,
                                    markersize=2,
                                    markerfacecolor=(1, 1, 0, 0.5),
                                )
                                ax.legend()
                            elif "tbl_mppt_events" in this_chan:
                                # this is all done per-data-point now
                                ax = None
                                fig = None
                            elif "tbl_ss_events" in this_chan:
                                # this is all done per-data-point now
                                ax = None
                                fig = None

                            # prepare the axes and queue up the redraw if needed
                            if ax:
                                [child.remove() for child in ax.get_children() if isinstance(child, MPLAnnotation)]  # delete annotations
                                ax.relim()
                                ax.autoscale()
                            if fig:
                                pass
                                # fig.canvas.draw_idle()

                            # drop expecdicts when it's safe (they're not involved in an ongoing sweep-series)
                            drop_these = []
                            for t_eid, expecdict in self.expecting.items():
                                t_did = expecdict["did"]
                                if t_did not in self.did_possibly_mid_series:
                                    drop_these.append(t_eid)

                            for t_eid in drop_these:
                                del self.expecting[t_eid]

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

    def minscroll(self):
        """move the scroll bar all the way to the left"""
        self.hscroller.props.hadjustment.props.value = 0

    def maxscroll(self):
        """move the scroll bar all the way to the right"""
        cv = self.hscroller.props.hadjustment.props.value  # check where we are now
        mv = self.hscroller.props.hadjustment.props.upper  # check the max value
        if cv != mv:  # only scroll if we need to
            self.hscroller.props.hadjustment.props.value = mv

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
            tr.name run_name,
            trd.device_id device_id,
            tss.name slot,
            tld.pad_no pad,
            ts.name user_label,
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
        join {self.db_schema_dot}tbl_runs tr on
            tr.id = trd.run_id
        join {self.db_schema_dot}tbl_users tu on
            tu.id = tr.user_id
        where
            trd.run_id = {rid}
        """
        try:
            with psycopg.connect(self.db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(query1)
                    for record in cur:
                        rcd = {}
                        for col, val in zip(cur.description, record):
                            rcd[col.name] = val
                        rcd["run_id"] = rid
                        data_row = DataRow(**rcd)
                        self.row_model.append(data_row)
                        self.known_devices[str(rcd["device_id"])] = rcd
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
