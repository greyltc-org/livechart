import random
import socket
import threading
import struct
import time


class Datagetter(object):
    """
    gets one data point at a time
    """

    _dtype = None  # "random" or "thermal"
    _zone = None
    _entered = None
    temp_file_name = None
    temp_file_object = None
    _last_val = None
    delay = 0.001

    def __init__(self, dtype="random", zone=1, delay=0.001):
        self.delay = delay
        self.zone = zone
        self.dtype = dtype
        _last_val = None
        self._stop_doer = threading.Event()
        self._want_new = threading.Event()

    def __enter__(self):
        self._entered = True
        if self._dtype == "thermal":
            self.temp_file_object = open(self.temp_file_name, "r")
        self._socket, self.socket = socket.socketpair()
        # self._reader, self._writer = await asyncio.open_connection(sock=_socket)
        _last_val = None
        self._stop_doer.clear()
        self._want_new.clear()
        self._doer = threading.Thread(group=None, target=self._socket_loop, daemon=True)
        self._doer.start()
        return self

    def __exit__(self, type, value, traceback):
        self._entered = False
        self._close_thermal_file()
        self._close_sockets()
        self._stop_doer.set()
        self._doer.join()
        self._stop_doer.clear()

    def _close_thermal_file(self):
        try:
            self.temp_file_object.close()
        except Exception as e:
            pass

    def _close_sockets(self):
        try:
            self._socket.close()
        except Exception as e:
            pass
        try:
            self.socket.close()
        except Exception as e:
            pass

    def _update_thermal(self):
        self.temp_file_name = f"/sys/class/thermal/thermal_zone{self._zone}/temp"
        if hasattr(self.temp_file_object, "closed"):
            if self.temp_file_object.closed == False:
                self.temp_file_object.close()
        if self._entered == True:
            self.temp_file_object = open(self.temp_file_name, "r")

    def trigger_new(self):
        self._want_new.set()

    def _socket_loop(self):
        while not self._stop_doer.is_set():
            if self._want_new.wait(timeout=0.1):  # this timeout is for how often we check for a stop request
                self._want_new.clear()
                self._socket.send(struct.pack("f", self.get))

    @property
    def zone(self):
        return self._zone

    @zone.setter
    def zone(self, value):
        if value != self._zone:
            self._zone = value
            self._update_thermal()

    @property
    def dtype(self):
        return self._dtype

    @dtype.setter
    def dtype(self, value):
        if value != self._dtype:
            if value == "thermal":
                self._dtype = value
                self._update_thermal()
            elif value == "random":
                self._dtype = value
                self._close_thermal_file()
            else:
                print("Warning: Unknown datatype")

    @property
    def get(self):
        if self._dtype == "thermal":
            try:
                point_int = int(self.temp_file_object.readline())
                self.temp_file_object.seek(0)
            except:
                point_int = float("nan")
        elif self._dtype == "random":
            point_int = random.randint(0, 100 * 1000)
        else:
            point_int = float("nan")
        if self.delay > 0:
            time.sleep(self.delay)  # insert fake delay to avoid too much cpu
        return point_int / 1000

    @property
    def thermaltype(self):
        if self._dtype == "thermal":
            try:
                type_file = f"/sys/class/thermal/thermal_zone{self._zone}/type"
                with open(type_file, "r") as fh:
                    type_str = fh.readline()
                result = type_str.strip()
            except Exception as e:
                result = "Unknown"
        elif self._dtype == "random":
            result = "Random"
        else:
            result = "None"
        return result


class Downsampler(object):
    """
    Feed this class high frequency data and every [factor]
    samples it will return an average of the last [factor] samples
    Can be used as an input filter to slow down datarate (and potentially increase precision)
    """

    factor = 5
    cache = []
    struct.unpack_from

    def __init__(self, factor=5):
        self.factor = factor
        self.cache = []

    def feed(self, input):
        if isinstance(input, tuple) or isinstance(input, list):
            self.cache += input
        else:
            self.cache.append(input)
        n_samples = len(self.cache)

        if n_samples >= self.factor:  # the cache is full, compute and return the average
            ret_val = sum(self.cache) / n_samples
            self.cache = []
        else:
            ret_val = float("nan")

        return ret_val
