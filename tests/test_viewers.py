import unittest
from livechart.viewers.ncurses import Interface as InterfaceN
import sys


class NcursesTestCase(unittest.TestCase):
    def test_init(self):
        iface = InterfaceN()
        self.assertIsInstance(iface, InterfaceN)

    def test_full_interface_random(self):
        """this should fail with pytest and in code ide"""
        cl_arg = "-1"
        if len(sys.argv) == 1:
            sys.argv.append(cl_arg)
        else:
            sys.argv[1] = cl_arg
        iface = InterfaceN()
        iface.max_duration = 3
        ret_code = iface.show()
        self.assertIsNone(ret_code)

    def test_full_interface_thermal(self):
        """this should fail on non-linux and with pytest and in code ide"""
        cl_arg = "0"
        if len(sys.argv) == 1:
            sys.argv.append(cl_arg)
        else:
            sys.argv[1] = cl_arg
        iface = InterfaceN()
        iface.max_duration = 3
        ret_code = iface.show()
        self.assertIsNone(ret_code)


class Gtk4TestCase(unittest.TestCase):
    def setUp(self) -> None:
        # do import in setUp() because gtk3.0 import clashes with 4.0 (the first one done will win)
        from livechart.viewers.gtk4 import Interface as Interface4

        self.interface = Interface4
        return super().setUp()

    def test_init(self):
        """This should fail if it runs in batch mode after the gtk3 case"""
        iface = self.interface()
        self.assertIsInstance(iface, self.interface)


class Gtk3TestCase(unittest.TestCase):
    def setUp(self) -> None:
        # do import in setUp() because gtk3.0 import clashes with 4.0 (the first one done will win)
        from livechart.viewers.gtk3 import Interface as Interface3

        self.interface = Interface3
        return super().setUp()

    def test_init(self):
        """This should fail if it runs in batch mode after the gtk4 case"""
        iface = self.interface()
        self.assertIsInstance(iface, self.interface)
