#!/usr/bin/env python3

import asyncio
import time
import json
import struct
import random
from enum import Enum, auto

from numpy import dtype

# from .lib import Datagetter


# import struct
class DType(Enum):
    RANDOM = auto()
    THERMAL = auto()


class LiveServer(object):
    host = "0.0.0.0"
    default_port = 58741
    srv = None
    clients = {}
    t0 = None
    dtype = DType.RANDOM
    zone_num = 0
    live_clients = asyncio.Event()
    delay = 0.001

    def __init__(self, host=host, port=default_port, data_type=dtype, thermal_zone=zone_num, artificial_delay=delay):
        self.host = host
        self.port = port
        self.dtype = data_type
        self.zone_num = thermal_zone
        self.delay = artificial_delay
        # self.srv = await asyncio.start_server(self.client_connected_cb, host=host, port=port, reuse_address=True)
        # self.srv = socketserver.TCPServer(server_address, socketserver.StreamRequestHandler, bind_and_activate=False)
        # self.srv.timeout = None  # never time out
        # self.srv.allow_reuse_address = True
        self.t0 = time.time()

    async def __aenter__(self):
        self.srv = await asyncio.start_server(self.client_connected_cb, host=self.host, port=self.port, reuse_address=True)
        print(f"Listening for clients on {(self.host, self.port)}")
        # self.srv.server_bind()
        # self.srv.server_activate()
        # self.sel.register(self.srv.socket, selectors.EVENT_READ, self.accept)
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        self.srv.close()
        await self.srv.wait_closed()
        # for r, w in self.clients:
        #    w.close()
        #    await w.wait_closed()

    async def client_connected_cb(self, reader, writer):
        pn = writer.get_extra_info("peername")
        self.clients[pn] = (reader, writer, asyncio.Queue())
        self.live_clients.set()
        task = asyncio.create_task(self.do_feeding(self.clients[pn][2], writer))
        print(f"New client = {pn}")
        while True:
            try:
                len_msg = await reader.readuntil(b"{")
            except asyncio.exceptions.IncompleteReadError:
                break
            try:
                msg_len = int(len_msg.decode()[:-1])
            except Exception as e:
                print("Stream parse error")
            else:
                the_rest = await reader.read(msg_len)
                if the_rest:
                    msg = "{" + the_rest.decode()
                    cmd = json.loads(msg)
                    print(f"I got {cmd} from {pn}")
                else:
                    break
        if len(self.clients) == 0:
            self.live_clients.clear()
        writer.close()
        await task
        await writer.wait_closed()
        del self.clients[pn]
        print(f"Goodbye to {pn}")

    async def datasource(self):
        while await self.live_clients.wait():
            if self.dtype == DType.RANDOM:
                value = random.random()
                await asyncio.sleep(self.delay)
            elif self.dtype == DType.THERMAL:
                value = random.random() * 10
                await asyncio.sleep(self.delay)
            else:
                value = 0
                await asyncio.sleep(self.delay)
            for pn, (reader, writer, q) in self.clients.items():
                if not writer.is_closing():
                    q.put_nowait(value)

    async def do_feeding(self, q: asyncio.Queue, writer: asyncio.StreamWriter):
        while not writer.is_closing():
            writer.write(struct.pack("f", await q.get()))
            await writer.drain()

    # def accept(self, sock):
    #    conn, addr = sock.accept()  # accept a connection
    #    print(f"Accepted new connection: {conn} from ip {addr}")
    #    # conn.setblocking(False)
    #    self.sel.register(conn, selectors.EVENT_READ, self.get_data)
    #    return (conn,)

    # def get_data(self, conn):
    #    try:
    #        data = conn.recv(1024)
    #    except Exception as e:
    #        data = None
    #    if data:
    #        pass
    #    else:  # must be a disconnect
    #        print("closing", conn)
    #        self.sel.unregister(conn)
    #        conn.close()
    #    return (conn, data)

    async def run(self):
        async with self.srv:
            await self.srv.serve_forever()


"""         with Datagetter(dtype=dtype, zone=zone) as dg:
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
                                        pass  # best effort """


async def amain():
    async with LiveServer() as ls:
        await asyncio.gather([ls.run, ls.datasource])


def main():
    asyncio.run(amain())


if __name__ == "__main__":
    main()
