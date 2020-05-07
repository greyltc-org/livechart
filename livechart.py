#!/usr/bin/env python3

import curses

import asciichartpy
import time
from collections import deque

"""
gets one data point. replace this with your own data fetcher
here it returns my CPU temperature (which only works in linux)
"""
def get_datapoint(delay = 0.001):
    temp_file = '/sys/class/thermal/thermal_zone1/temp'
    with open(temp_file,'r') as fh:
        tmp_str = fh.readline()
    time.sleep(delay) # build in a delay so we don't slam the CPU
    return int(tmp_str)/1000


class Downsampler:
    """
    Feed this class high frequency data and every [factor]
    samples it will return an average of the last [factor] samples
    Can be used as an input filter to slow down datarate (and potentially increase precision)
    """
    def __init__(self, factor = 5):
        self.factor = factor
        self.cache = []
        self.next_sample = 0
    
    def feed(self, sample):
        self.next_sample += 1
        self.cache.append(sample)

        if self.next_sample == self.factor: # the cache is full, compute and return the average
            ret_val = sum(self.cache)/float(self.factor)
            self.next_sample = 0
            self.cache = []
        else:
            ret_val = None
        
        return ret_val


def main(stdscr):
    # Clear screen
    stdscr.clear() # clear the screen
    stdscr.nodelay(True) # don't wait for input
    curses.curs_set(0) # hide the cursor

    quit_key = 'q'

    # in characters 
    plot_width = 100
    plot_height = 30
    # TODO: read the terminal size with curses and use that

    average_window_length = round(plot_width/5) # length of running average window
    downsample_by = 30 # factor for downsampling

    display = deque([], plot_width) # what we'll be displaying

    cache = deque() # used in calculating the rolling mean
    cum_sum = 0 # used for calculating rolling mean
    ds = Downsampler(downsample_by)

    while True:
        stdscr.erase()

        #this_data = get_datapoint() 
        raw_data = get_datapoint() # get a new datapoint
        while (this_data := ds.feed(raw_data)) is None: # feed the downsampler with raw data until it gives us a data point
            raw_data = get_datapoint() # get a new datapoint

        # do rolling average computation
        cache.append(this_data)
        cum_sum += this_data
        if len(cache) < average_window_length:
            pass
        else:
            cum_sum -= cache.popleft()
        this_avg = cum_sum/float(len(cache))

        # draw the plot
        to_display = this_avg
        #to_display = this_data
        stdscr.addstr(0, 0, f"CPU Temperature = {to_display:.2f}°C     ===== press {quit_key} to quit =====")
        display.append(to_display)
        stdscr.addstr(1, 0, asciichartpy.plot(display, {'height': plot_height}))
        stdscr.refresh()

        ch =  stdscr.getch()
        if ch == ord(quit_key): # q key ends the program
            break
        elif ch == ord('r'): # r key does nothing
            pass

if __name__ == "__main__":
    curses.wrapper(main)
