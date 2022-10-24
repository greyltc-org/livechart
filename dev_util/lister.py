import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gio, GObject, Gtk  # noqa


class Country(GObject.Object):
    __gtype_name__ = "Country"

    def __init__(self, country_id, country_name, pm):
        super().__init__()

        self._country_id = country_id
        self._country_name = country_name
        self._country_pm = pm

    @GObject.Property(type=str)
    def country_id(self):
        return self._country_id

    @GObject.Property(type=str)
    def country_name(self):
        return self._country_name

    @GObject.Property(type=str)
    def country_pm(self):
        return self._country_pm

    def __repr__(self):
        return f"Country(country_id={self.country_id}, country_name={self.country_name})"  # noqa


class ExampleWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="DropDown", default_width=300)

        nodes = {
            "au": ("Austria", "Kern"),
            "uk": ("United Kingdom", "Truss"),
            "us": ("United States", "Trump"),
        }

        self.model = Gio.ListStore(item_type=Country)
        for n in nodes.keys():
            self.model.append(Country(country_id=n, country_name=nodes[n][0], pm=nodes[n][1]))

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_factory_setup)
        factory.connect("bind", self._on_factory_bind, "country_name")
        factory.connect("unbind", self._on_factory_unbind)

        factory2 = Gtk.SignalListItemFactory()
        factory2.connect("setup", self._on_factory_setup)
        factory2.connect("bind", self._on_factory_bind, "country_pm")
        factory2.connect("unbind", self._on_factory_unbind)

        self.cv = Gtk.ColumnView.new(Gtk.NoSelection.new(self.model))
        col1 = Gtk.ColumnViewColumn.new("Country", factory)
        col1.props.fixed_width = 120
        self.cv.append_column(col1)
        col2 = Gtk.ColumnViewColumn.new("PM", factory2)
        col2.props.fixed_width = 80
        self.cv.append_column(col2)

        box = Gtk.Box(spacing=12, hexpand=True, vexpand=True, valign=Gtk.Align.CENTER)
        box.props.margin_start = 12
        box.props.margin_end = 12
        box.props.margin_top = 6
        box.props.margin_bottom = 6
        box.append(Gtk.Label(label="Some Table:"))
        box.append(self.cv)

        self.set_child(box)

    def _on_factory_setup(self, factory, list_item):
        cell = Gtk.Inscription()
        list_item.set_child(cell)

    def _on_factory_bind(self, factory, list_item, what):
        cell = list_item.get_child()
        country = list_item.get_item()
        print(country)
        binding = country.bind_property(what, cell, "text", GObject.BindingFlags.SYNC_CREATE)
        cell.binding = binding

    def _on_factory_unbind(self, factory, list_item):
        cell = list_item.get_child()
        cell.binding.unbind()
        print("unbound")

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
