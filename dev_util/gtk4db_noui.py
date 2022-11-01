import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GObject

from typing import Generator


class DataRow(GObject.Object):
    """table row class"""

    __gtype_name__ = "DataRow"
    col_defs = [
        {"name": "a", "title": "A"},
        {"name": "b", "title": "B"},
        {"name": "c", "title": "C"},
        {"name": "d", "title": "D"},
        {"name": "e", "title": "E"},
        {"name": "f", "title": "F"},
        {"name": "g", "title": "G"},
        {"name": "h", "title": "H"},
        {"name": "i", "title": "I"},
        {"name": "j", "title": "J"},
    ]
    # data = {}

    def __init__(self, **kwargs):
        super().__init__()
        self.data = {}
        for col in self.col_defs:
            self.data[col["name"]] = "n/a"

        for key, val in kwargs.items():
            if key in self.data:
                self.data[key] = val

    # TODO: possibly try to use a class factory or something for all these instead of doing them manually
    @GObject.Property(type=str)
    def a(self):
        return self.data["a"]

    @GObject.Property(type=str)
    def b(self):
        return self.data["b"]

    @GObject.Property(type=str)
    def c(self):
        return self.data["c"]

    @GObject.Property(type=str)
    def d(self):
        return self.data["d"]

    @GObject.Property(type=str)
    def e(self):
        return self.data["e"]

    @GObject.Property(type=str)
    def f(self):
        return self.data["f"]

    @GObject.Property(type=str)
    def g(self):
        return self.data["g"]

    @GObject.Property(type=str)
    def h(self):
        return self.data["h"]

    @GObject.Property(type=str)
    def i(self):
        return self.data["i"]

    @GObject.Property(type=str)
    def j(self):
        return self.data["j"]


class Interface(object):
    app = None
    row_model = Gio.ListStore.new(DataRow)
    dat_seq: Generator[int, int | None, None]
    n_rows_to_add = 10

    def __init__(self):
        app_id = "org.testing"
        self.app = Gtk.Application(application_id=app_id, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.app.connect("activate", self.on_app_activate)
        self.countsup = Interface.counter_sequence()

    def on_app_activate(self, app):
        win = self.app.props.active_window
        if not win:
            win = Gtk.ApplicationWindow.new(app)
            win.props.default_height = 480
            win.props.default_width = 640

            win.set_application(app)
            win.props.title = f"testing"

            main_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)
            main_box.spacing = 5
            main_box.props.vexpand = True
            main_box.props.vexpand_set = True

            cv = Gtk.ColumnView.new(Gtk.MultiSelection.new(self.row_model))
            cv.props.show_row_separators = True
            cv.props.show_column_separators = True
            cv.props.reorderable = False
            cv.props.vexpand = True
            cv.props.enable_rubberband = True
            cv.props.halign = Gtk.Align.CENTER

            names = [col["name"] for col in DataRow.col_defs]
            titles = [col["title"] for col in DataRow.col_defs]

            self.factories = []
            self.cvcs = []
            for name, title in zip(names, titles):
                factory = Gtk.SignalListItemFactory()
                factory.connect("setup", self._on_factory_setup)
                factory.connect("bind", self._on_factory_bind, name)
                factory.connect("unbind", self._on_factory_unbind)
                factory.connect("teardown", self._on_factory_teardown)
                cvc = Gtk.ColumnViewColumn(title=title, factory=factory)
                cvc.props.expand = True
                cv.append_column(cvc)
                self.factories.append(factory)
                self.cvcs.append(cvc)

            sw = Gtk.ScrolledWindow.new()
            sw.props.propagate_natural_width = True
            sw.props.child = cv
            main_box.append(sw)
            btn = Gtk.Button.new_with_label(f"Add {self.n_rows_to_add} Rows")
            btn.connect("clicked", self.add_rows)
            main_box.prepend(btn)

            win.set_child(main_box)

        win.present()

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
        cell._binding = None

    def add_rows(self, btn):
        for i in range(self.n_rows_to_add):
            row_n = next(self.countsup)
            print(f"added row#: {row_n}")
            self.row_model.append(DataRow(a=str(row_n)))

    @staticmethod
    def counter_sequence(start: int = 0) -> Generator[int, int | None, None]:
        """infinite upwards integer sequence generator"""
        c = start
        while True:
            yield c
            c += 1

    def run(self):
        self.app.run()


def main():
    iface = Interface()
    iface.run()


if __name__ == "__main__":
    main()
