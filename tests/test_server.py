import unittest
from livechart.server import LiveServer


class LiveServerTestCase(unittest.TestCase):
    def test_init(self):
        ls = LiveServer()
        self.assertIsInstance(ls, LiveServer)

    def test_connect(self):
        ls = LiveServer()
        self.assertIsInstance(ls, LiveServer)
        ls.connect()

    def test_run(self):
        runtime = 5  # seconds
        ls = LiveServer()
        self.assertIsInstance(ls, LiveServer)
        ls.connect()
        ls.run(timeout=runtime)
