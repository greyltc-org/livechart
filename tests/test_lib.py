import unittest
from livechart.lib import Datagetter
from livechart.lib import Downsampler
import statistics
import math


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
        with Datagetter(dtype="thermal", zone=0) as dg:
            value = dg.get
        self.assertIsInstance(value, float)

    def test_linux_temp_setters(self):
        """only works in linux"""
        with Datagetter() as dg:
            dg.dtype = "thermal"
            dg.zone = 0
            value = dg.get
        self.assertIsInstance(value, float)

    def test_linux_temp_sensor_string(self):
        """only works in linux"""
        with Datagetter(dtype="thermal", zone=0) as dg:
            value = dg.thermaltype
        self.assertIsInstance(value, str)


class DownsamplerTestCase(unittest.TestCase):
    def test_feed(self):
        ds_factor = 5
        ds = Downsampler(factor=ds_factor)
        sequence = range(ds_factor)
        for sample, i in enumerate(sequence):
            if i == ds_factor - 1:
                break
            else:
                self.assertTrue(math.isnan(ds.feed(sample)))
        self.assertEqual(statistics.mean(sequence), ds.feed(sequence[-1]))
