#!/usr/bin/env python3

import socketserver
import selectors
import time
from .lib import Datagetter
import json

# import struct


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
        print(f"Listening for clients on {self.srv.server_address}")
        self.srv.server_bind()
        self.srv.server_activate()
        self.sel.register(self.srv.socket, selectors.EVENT_READ, self.accept)

    def accept(self, sock):
        conn, addr = sock.accept()  # accept a connection
        print(f"Accepted new connection: {conn} from ip {addr}")
        # conn.setblocking(False)
        self.sel.register(conn, selectors.EVENT_READ, self.get_data)
        return (conn,)

    def get_data(self, conn):
        try:
            data = conn.recv(1024)
        except Exception as e:
            data = None
        if data:
            pass
        else:  # must be a disconnect
            print("closing", conn)
            self.sel.unregister(conn)
            conn.close()
        return (conn, data)

    def run(self, timeout=float("inf"), dtype="thermal", zone=8):
        with Datagetter(dtype=dtype, zone=zone) as dg:
            self.sel.register(dg.socket, selectors.EVENT_READ, self.get_data)
            while (time.time() - self.t0) < timeout:
                events = self.sel.select(timeout=0.5)  # timeout is how often to check for timed exit
                for key, mask in events:
                    callback = key.data
                    callback_return = callback(key.fileobj)
                    if len(callback_return) == 1:
                        # new client
                        conn = callback_return
                        if len(self.clients) == 0:
                            dg.trigger_new()  # special data request on 0 -> 1 client transition
                        self.clients.append(conn[0])
                    else:  # len will be 2 if not new client
                        # data from connected client
                        conn, data = callback_return
                        if conn in self.clients:
                            if (not data) or (conn._closed):  # client diconnect
                                print(f"Cleaning up client #{self.clients.index(conn)}, {conn}")
                                del self.clients[self.clients.index(conn)]
                            else:
                                try:
                                    cmd = json.loads(data.decode())
                                    if "dtype" in cmd:
                                        dg.dtype = cmd["dtype"]
                                    if "zone" in cmd:
                                        dg.zone = cmd["zone"]
                                    if "delay" in cmd:
                                        dg.delay = cmd["delay"]
                                    if "thermaltype" in cmd:
                                        conn.send(f"{dg.thermaltype}\n".encode())
                                except Exception as e:
                                    # unexpected client data?
                                    print(f"New data from client #{self.clients.index(conn)}, {conn}: {data}")
                        else:  # data from getter
                            # print(f"Got new value = {struct.unpack('f', data)[0]}")
                            if len(self.clients) > 0:
                                dg.trigger_new()  # clients exist, so we'll ask for new data
                                for c in self.clients:
                                    try:
                                        c.send(data)  # relay the data to all clients
                                    except Exception as e:
                                        pass  # best effort

    def serve(self):
        self.connect()
        self.run()


def main():
    ls = LiveServer()
    ls.serve()


if __name__ == "__main__":
    main()
