#!/usr/bin/env python3
import curses
import time
import asciichartpy
from collections import deque
import sys
import os
import math
import struct
import selectors
import asyncio
import json

# from ..server import LiveServer
from ..lib import Downsampler


class Interface(object):
    dg = None
    thermal_zone_number = None
    dtype = None
    max_duration = float("inf")  # s

    def __init__(self):
        if "ix" in os.name:
            if len(sys.argv) > 1:
                try:
                    self.thermal_zone_number = int(sys.argv[1])
                    self.dtype = "thermal"
                except Exception as e:
                    pass
        else:
            self.thermal_zone_number = 1
            self.dtype = "random"

        if self.thermal_zone_number == -1:
            self.dtype = "random"

    def do_curse(self, stdscr, dtype="random", zone=1):
        # Clear screen
        stdscr.clear()  # clear the screen
        stdscr.nodelay(True)  # don't wait for input
        curses.curs_set(0)  # hide the cursor
        thermal_zone_number = zone

        quit_key = "q"

        # delay = 0.001

        # in characters
        plot_width = 100
        plot_height = 30
        # TODO: read the terminal size with curses and use that

        average_window_length = round(plot_width / 5)  # length of running average window
        downsample_by = 30  # factor for downsampling

        display = deque([], plot_width)  # what we'll be displaying

        cache = deque()  # used in calculating the rolling mean
        cum_sum = 0  # used for calculating rolling mean
        ds = Downsampler(downsample_by)
        # sel = selectors.DefaultSelector()

        asyncio.run(self.synchy(ds, stdscr, cache, average_window_length, cum_sum, display, quit_key, plot_height, thermal_zone_number, dtype))

    async def synchy(self, lds, lstdscr, lcache, awinlen, lcum_sum, ldisp, lquitkey, ph, tzn, datatype):
        reader, writer = await asyncio.open_connection("127.0.0.1", 58741)
        tmp_type = datatype
        writer.write(json.dumps({"dtype": datatype, "zone": tzn, "delay": 0}).encode())
        t0 = time.time()
        quit = False
        # dg.trigger_new()  # ask for a new value
        while (not quit) and ((time.time() - t0) < self.max_duration):
            vraw = await reader.read(4)
            raw_data = struct.unpack("f", vraw)[0]  # TODO: possibly handle more than one AND check this length
            if math.isnan(this_data := lds.feed(raw_data)):  # feed the downsampler with raw data until it gives us a data point
                pass
            else:  # the downsampler as produced a point for us
                lstdscr.erase()

                # do rolling average computation
                lcache.append(this_data)
                lcum_sum += this_data
                if len(lcache) < awinlen:
                    pass
                else:
                    lcum_sum -= lcache.popleft()
                this_avg = lcum_sum / float(len(lcache))

                # draw the plot
                to_display = this_avg
                # to_display = this_data
                lstdscr.addstr(0, 0, f"{tmp_type} Temperature = {to_display:.2f}°C     ===== press {lquitkey} to quit =====")
                ldisp.append(to_display)
                lstdscr.addstr(1, 0, asciichartpy.plot(ldisp, {"height": ph}))
                lstdscr.refresh()

            ch = lstdscr.getch()
            if ch == ord(lquitkey):  # q key ends the program
                quit = True
            elif ch == ord("r"):  # r key does nothing
                pass

    def show(self):
        if self.dtype is not None:
            dtype = self.dtype
            thermal_zone_number = self.thermal_zone_number
        else:
            print("Enter 1 for random data or 0 for thermal data [1]: ", end="")
            user = input()
            if user == "":
                user = "1"
                print(user)

            if user == "0":
                dtype = "thermal"
            elif user == "1":
                dtype = "random"
            else:
                raise ValueError(f"{user} is not 0 or 1")

            if user == "0":
                print()
                os.system("bash -c \"paste <(ls /sys/class/thermal/ | grep thermal_zone) <(cat /sys/class/thermal/thermal_zone*/type) <(cat /sys/class/thermal/thermal_zone*/temp) | column -s $'\t' -t | sed 's/\(.\)..$/.\1°C/'\"")
                print("Pick a thermal zone number to monitor [0-N]: ", end="")
                user = input()
                if user == "":
                    user = "0"
                    print(user)
                thermal_zone_number = int(user)
            else:
                thermal_zone_number = 1

        return curses.wrapper(self.do_curse, dtype=dtype, zone=thermal_zone_number)


def main():
    iface = Interface()
    return iface.show()


if __name__ == "__main__":
    sys.exit(main())
