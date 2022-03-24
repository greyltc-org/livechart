#!/usr/bin/env python3

import socketserver
import selectors
import socket
import time
import io
from .lib import Datagetter

# from .lib import Downsampler


class LiveServer(object):
    sel = selectors.DefaultSelector()  # global selector
    default_port = 58741
    srv = None
    clients = []
    t0 = None

    def __init__(self, server_address=("0.0.0.0", default_port)):
        self.srv = socketserver.TCPServer(server_address, socketserver.StreamRequestHandler, bind_and_activate=False)
        self.srv.timeout = None  # never time out
        self.srv.allow_reuse_address = True
        self.t0 = time.time()

    def connect(self):
        self.srv.server_bind()
        self.srv.server_activate()
        self.sel.register(self.srv.socket, selectors.EVENT_READ, self.accept)

    def accept(self, sock):
        conn, addr = sock.accept()  # accept a connection
        print(f"Accepted new connection: {conn} from ip {addr}")
        conn.setblocking(False)
        self.sel.register(conn, selectors.EVENT_READ, self.get_data)
        return (conn,)

    def get_data(self, conn):
        data = conn.recv(1024)  # Should be ready
        if data:
            pass
        else:  # must be a disconnect
            print("closing", conn)
            self.sel.unregister(conn)
            conn.close()
        return (conn, data)

    def get_temp(self, f):
        data = f.readline()
        f.seek(0)
        return (f, data)

    def run(self, timeout=float("inf"), dtype="thermal", zone=1):
        with Datagetter(dtype=dtype, zone=zone) as dg:
            self.sel.register(dg.temp_file_object, selectors.EVENT_READ, self.get_temp)
            while (time.time() - self.t0) < timeout:
                events = self.sel.select()
                for key, mask in events:
                    callback = key.data
                    callback_return = callback(key.fileobj)
                    if isinstance(callback_return[0], socket.socket):  # network evengt
                        if len(callback_return) == 1:
                            # new client
                            conn = callback_return
                            self.clients.append(conn)
                        else:  # len will be 2
                            # data from connected client
                            conn, data = callback_return
                            if conn in self.clients:
                                if not conn._closed:
                                    print(f"New data from client #{self.clients.index(conn)}, {conn}: {data}")
                                else:
                                    print(f"Cleaning up client #{self.clients.index(conn)}, {conn}")
                                    del self.clients[self.clients.index(conn)]
                            else:
                                print("Unknown client!")
                    elif isinstance(callback_return[0], io.IOBase):
                        td = callback_return[1]
                        if len(td) > 0:
                            print(f"Tmpdat = {callback_return[1]}")
                    else:
                        print("Unexpected event!")

                # val = dg.get
                # pass

    def serve(self):
        self.connect()
        self.run()


def main():
    ls = LiveServer()
    ls.serve()


if __name__ == "__main__":
    main()
