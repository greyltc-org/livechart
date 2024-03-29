#!/usr/bin/env python3

import asyncio
import time
import json
import struct
import random
import psycopg
from enum import Enum, auto

from numpy import dtype

from .db import DBTool


# import struct
class DType(Enum):
    RANDOM = auto()
    THERMAL = auto()
    DB = auto()


class LiveServer(object):
    host = "0.0.0.0"
    default_port = 58741
    srv = None
    clients = {}
    t0 = None
    dtype = DType.RANDOM
    zone_num = 0
    live_clients = asyncio.Event()  # set when there is at least one connected client
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

    async def client_connected_cb(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        pn = writer.get_extra_info("peername")
        self.clients[pn] = (reader, writer, asyncio.Queue())
        self.live_clients.set()
        feeder = asyncio.create_task(self.do_feeding(*self.clients[pn]))
        print(f"New client = {pn}")
        while True:
            try:
                len_msg = await reader.readuntil(b"{")
            except asyncio.exceptions.IncompleteReadError:
                break
            except Exception as e:
                print(f"Handled exception A: {e}")
                break
            try:
                msg_len = int(len_msg.decode()[:-1])
            except Exception as e:
                print("Stream parse error. Resyncing...")
            else:
                try:
                    the_rest = await reader.read(msg_len)
                except asyncio.exceptions.IncompleteReadError:
                    break
                except Exception as e:
                    print(f"Handled exception B: {e}")
                    break
                else:
                    msg = "{" + the_rest.decode()
                    cmd = json.loads(msg)
                    if "thermaltype" in cmd:
                        writer.write(f"some_zone\n".encode())  # TODO: use right zone
                    print(f"I got {cmd} from {pn}")
        try:
            await asyncio.wait_for(feeder, timeout=0.5)
        except:
            print("Feeder termination timeout")
        if not feeder.done():
            feeder.cancel()
        try:
            await feeder
        except asyncio.CancelledError:
            print("Had to cancel feeder")
        if len(self.clients) == 1:
            self.live_clients.clear()
        del self.clients[pn]
        print(f"Goodbye to {pn}")

    async def datasource(self):
        dbw = DBTool()
        dbw.listen_channels.append(f"{dbw.tbl_name}_events")
        aconn = await psycopg.AsyncConnection.connect(conninfo=dbw.db_uri, autocommit=True)
        async with aconn:
            async with aconn.cursor() as acur:
                listener = asyncio.create_task(dbw.do_listening(aconn, acur))
                while await self.live_clients.wait():  # runs forever
                    if self.dtype == DType.DB:
                        if dbw.outq.qsize() > 1:
                            vals = [await dbw.outq.get() for x in range(dbw.outq.qsize())]
                        else:
                            vals = (await dbw.outq.get(),)
                    elif self.dtype == DType.RANDOM:
                        vals = (random.random(),)
                        await asyncio.sleep(self.delay)
                    elif self.dtype == DType.THERMAL:
                        vals = (random.random() * 10,)
                        await asyncio.sleep(self.delay)
                    else:
                        vals = (0,)
                        await asyncio.sleep(self.delay)
                    self.putter(vals)
                await listener  # will never be reached

    def putter(self, vals):
        """distributes values to client queues"""
        for pn, (reader, writer, q) in self.clients.items():
            for v in vals:
                if not writer.is_closing():
                    q.put_nowait(v)

    async def do_feeding(self, reader: asyncio.StreamWriter, writer: asyncio.StreamReader, q: asyncio.Queue):
        while not reader.at_eof():
            q_item = await q.get()
            try:
                writer.write(struct.pack("f", q_item[2]))
                await writer.drain()
            except Exception as e:
                print(f"Write exception: {e}")
        try:
            writer.close()
            await writer.wait_closed()
        except Exception as e:
            print(f"Writer close exception: {e}")

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
    async with LiveServer(data_type=DType.DB) as ls:
        await asyncio.gather(ls.run(), ls.datasource())


def main():
    asyncio.run(amain())


if __name__ == "__main__":
    main()
