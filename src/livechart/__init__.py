"""Real time data plotting with python (in the terminal with curses and asciichart)"""
from importlib.metadata import version

try:
    __version__ = version("livechart")
except:
    __version__ = "0.0.0"
