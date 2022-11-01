import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gio, GObject, Gtk  # noqa


class DataRow(GObject.Object):
    """table row class"""

    __gtype_name__ = "DataRow"
    # cols = {
    #     "user": {"value": "", "title": "User", "width": 120},
    #     "run_id": {"value": "", "title": "Run ID", "width": None},
    #     "slot": {"value": "", "title": "Slot", "width": None},
    #     "pad": {"value": "", "title": "Pad", "width": None},
    #     "user_label": {"value": "", "title": "Label", "width": None},
    #     "area": {"value": "", "title": "Area[cm^2]", "width": None},
    #     "dark_area": {"value": "", "title": "Dark Area[cm^2]", "width": None},
    #     "voc_ss": {"value": "", "title": "V_oc[V]", "width": None},
    #     "jsc_ss": {"value": "", "title": "J_sc[mA/cm^2]", "width": None},
    #     "pmax_ss": {"value": "", "title": "P_max[mW/cm^2]", "width": None},
    # }

    def __init__(self, **kwargs):
        super().__init__()
        self.cols = {
            "user": {"value": "", "title": "User", "width": 120},
            "run_id": {"value": "", "title": "Run ID", "width": None},
            "slot": {"value": "", "title": "Slot", "width": None},
            "pad": {"value": "", "title": "Pad", "width": None},
            "user_label": {"value": "", "title": "Label", "width": None},
            "area": {"value": "", "title": "Area[cm^2]", "width": None},
            "dark_area": {"value": "", "title": "Dark Area[cm^2]", "width": None},
            "voc_ss": {"value": "", "title": "V_oc[V]", "width": None},
            "jsc_ss": {"value": "", "title": "J_sc[mA/cm^2]", "width": None},
            "pmax_ss": {"value": "", "title": "P_max[mW/cm^2]", "width": None},
        }
        for key, val in kwargs.items():
            if "area" in key:
                val = round(val, 4)
            self.cols[key]["value"] = val

    # TODO: possibly try to use a class factory or something for all these instead of doing them manually
    @GObject.Property(type=str)
    def user_label(self):
        return self.cols["user_label"]["value"]

    @GObject.Property(type=str)
    def slot(self):
        return self.cols["slot"]["value"]

    @GObject.Property(type=str)
    def pad(self):
        return self.cols["pad"]["value"]

    @GObject.Property(type=str)
    def run_id(self):
        return self.cols["run_id"]["value"]

    @GObject.Property(type=str)
    def user(self):
        return self.cols["user"]["value"]

    @GObject.Property(type=str)
    def area(self):
        return self.cols["area"]["value"]

    @GObject.Property(type=str)
    def dark_area(self):
        return self.cols["dark_area"]["value"]

    @GObject.Property(type=str)
    def voc_ss(self):
        return self.cols["voc_ss"]["value"]

    @GObject.Property(type=str)
    def jsc_ss(self):
        return self.cols["jsc_ss"]["value"]

    @GObject.Property(type=str)
    def pmax_ss(self):
        return self.cols["pmax_ss"]["value"]


class ExampleWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Column View", default_width=300)
        # self.cols = []

        nodes = {
            "au": ("Austria", "Van der Bellen"),
            "uk": ("United Kingdom", "Charles III"),
            "us": ("United States", "Biden"),
        }

        self.model = Gio.ListStore(item_type=DataRow)
        for n in nodes.keys():
            self.model.append(DataRow(user=nodes[n][1]))
            print(nodes[n][1])

        for row in self.model:
            print(row.user)

        self.cv = Gtk.ColumnView.new(Gtk.NoSelection(model=self.model))
        self.cv.props.hexpand = True
        self.cv.props.vexpand = True
        self.cv.props.show_row_separators = True
        self.cv.props.show_column_separators = True

        example_row = DataRow()

        for name, col in example_row.cols.items():
            a_dict = {}
            a_dict["factory"] = Gtk.SignalListItemFactory()
            a_dict["factory"].connect("setup", self._on_factory_setup)
            a_dict["factory"].connect("bind", self._on_factory_bind, name)
            a_dict["factory"].connect("unbind", self._on_factory_unbind)
            a_dict["factory"].connect("teardown", self._on_factory_teardown)
            a_dict["cvc"] = Gtk.ColumnViewColumn(title=col["title"], factory=a_dict["factory"])

            if col["width"]:
                a_dict["cvc"].props.fixed_width = col["width"]
            else:
                a_dict["cvc"].props.expand = True
            self.cv.append_column(a_dict["cvc"])
            # self.cols.append(a_dict)

        # factory = Gtk.SignalListItemFactory()
        # factory.connect("setup", self._on_factory_setup)
        # factory.connect("bind", self._on_factory_bind, "country_name")
        # factory.connect("unbind", self._on_factory_unbind, "country_name")
        # factory.connect("teardown", self._on_factory_teardown)

        # factory2 = Gtk.SignalListItemFactory()
        # factory2.connect("setup", self._on_factory_setup)
        # factory2.connect("bind", self._on_factory_bind, "country_pm")
        # factory2.connect("unbind", self._on_factory_unbind, "country_pm")
        # factory2.connect("teardown", self._on_factory_teardown)

        # self.cv = Gtk.ColumnView(model=Gtk.NoSelection(model=self.model))
        # col1 = Gtk.ColumnViewColumn(title="Country", factory=factory)
        # col1.props.expand = True
        # self.cv.append_column(col1)
        # col2 = Gtk.ColumnViewColumn(title="Head of State", factory=factory2)
        # col2.props.expand = True
        # self.cv.append_column(col2)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, valign=Gtk.Align.CENTER)
        box.props.margin_start = 12
        box.props.margin_end = 12
        box.props.margin_top = 6
        box.props.margin_bottom = 6
        box.append(Gtk.Label(label="Some Table:"))
        sw = Gtk.ScrolledWindow.new()
        sw.props.height_request = 600
        sw.props.child = self.cv
        box.append(sw)

        btn = Gtk.Button.new_with_label("Add Rows")
        btn.connect("clicked", self.add_rows)
        box.prepend(btn)
        self.new_rows = 0

        self.set_child(box)

    def add_rows(self, btn):
        n = 10
        for i in range(n):
            self.new_rows += 1
            self.model.append(DataRow(user=str(self.new_rows)))
            # self.new_rows += 1

    def _on_factory_setup(self, factory, list_item):
        cell = Gtk.Inscription()
        cell._binding = None
        list_item.set_child(cell)

    def _on_factory_bind(self, factory, list_item, what):
        cell = list_item.get_child()
        country = list_item.get_item()
        cell._binding = country.bind_property(what, cell, "text", GObject.BindingFlags.SYNC_CREATE)
        print(f"bind/rebind {self.new_rows}")

    def _on_factory_unbind(self, factory, list_item):
        cell = list_item.get_child()
        if cell._binding:
            cell._binding.unbind()
            cell._binding = None
            print("unbinding")

    def _on_factory_teardown(self, factory, list_item):
        cell = list_item.get_child()
        cell._binding = None
        print("downtearing")

    def _on_selected_item_notify(self, dropdown, _):
        country = dropdown.get_selected_item()
        print(f"Selected item: {country}")


class ExampleApp(Adw.Application):
    def __init__(self):
        super().__init__()
        self.window = None

    def do_activate(self):
        if self.window is None:
            self.window = ExampleWindow(self)
        self.window.present()


app = ExampleApp()
app.run([])
