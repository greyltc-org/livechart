import unittest
from livechart.lib import Datagetter

class DatagetterTestCase(unittest.TestCase):
    def test_default_get(self):
        dg = Datagetter()
        value = dg.get
        self.assertIsInstance(value, float)

    def test_default_context(self):
        with Datagetter() as dg:
            value = dg.get
        self.assertIsInstance(value, float)
    
    def test_linux_temp_fetch(self):
        """only works in linux"""
        with Datagetter(dtype='thermal', zone=1) as dg:
            value = dg.get
        self.assertIsInstance(value, float)