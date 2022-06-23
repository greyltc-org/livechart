import json
import psycopg
import getpass
import asyncio
import datetime as dt
import random
from typing import Optional, Tuple


class ThermalSource(object):
    """System thermal data source class"""

    _zone_num = 7
    delay = 0.001
    _temp_file_object = None

    def __init__(self, thermal_zone=_zone_num, artificial_delay=delay):
        self._zone_num = thermal_zone
        self.delay = artificial_delay

    async def __aenter__(self) -> "ThermalSource":
        await self._update_thermal()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> Optional[bool]:
        try:
            self._temp_file_object.close()
        except Exception as e:
            pass
        return True

    async def _update_thermal(self):
        temp_file_name = f"/sys/class/thermal/thermal_zone{self._zone_num}/temp"
        if hasattr(self._temp_file_object, "closed"):
            if self._temp_file_object.closed == False:
                if self._temp_file_object.name == temp_file_name:
                    return
                self._temp_file_object.close()
        self._temp_file_object = open(temp_file_name, "r")

    async def get(self) -> Tuple[dt.datetime, float]:
        await asyncio.sleep(self.delay)
        point_int = int(self._temp_file_object.readline())
        self._temp_file_object.seek(0)
        return (dt.datetime.now(), point_int / 1000)

    @property
    def thermaltype(self):
        try:
            type_file = f"/sys/class/thermal/thermal_zone{self._zone_num}/type"
            with open(type_file, "r") as fh:
                type_str = fh.readline()
            result = type_str.strip()
        except Exception as e:
            result = "Unknown"
        return result

    @property
    def zone(self):
        return self._zone_num

    @zone.setter
    def zone(self, value):
        if value != self._zone_num:
            self._zone_num = value
            self._update_thermal()


class RandomSource(object):
    """Random data source class"""

    delay: float = 0.001

    def __init__(self, artificial_delay: float = delay) -> None:
        self.delay = artificial_delay

    async def __aenter__(self) -> "RandomSource":
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> Optional[bool]:
        return True

    async def get(self) -> Tuple[dt.datetime, float]:
        await asyncio.sleep(self.delay)
        return (dt.datetime.now(), random.random())


class DBTool(object):
    db_proto = "postgresql://"
    db_user = None
    db_name = None
    db_host = None
    db_port = 5432
    db_uri = None
    listen_channels = []
    tbl_name = "tbl_time_data"
    stop_relay: bool = False  # signal to stop relay

    def __init__(self, db_proto=db_proto, db_user=db_user, db_name=db_name, db_host=db_host, db_port=db_port, db_uri=db_uri):

        # https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING
        if db_uri is not None:  # all connection params are overwritten by using this
            self.db_uri = db_uri
        else:
            if db_proto is None:
                self.db_proto = "postgresql://"
            else:
                self.db_proto = db_proto
            self.db_uri = self.db_proto
            if db_user is None:
                self.db_user = getpass.getuser()
            else:
                self.db_user = db_user
            self.db_uri = self.db_uri + f"{self.db_user}@"
            if db_host is None:
                self.db_host = ""
            else:
                self.db_host = db_host
            self.db_uri = self.db_uri + self.db_host
            if self.db_host != "":
                if db_port is None:
                    self.db_port = 5432
                else:
                    self.db_port = db_port
                self.db_uri = self.db_uri + f":{self.db_port}"
            if db_name is None:
                self.db_name = getpass.getuser()
            else:
                self.db_name = db_name
            self.db_uri = self.db_uri + f"/{self.db_name}"
        self.outq = asyncio.Queue()

    async def run_backend(self, timeout=5, fake_delay=0.001):
        aconn = await psycopg.AsyncConnection.connect(conninfo=self.db_uri, autocommit=True)
        async with aconn:
            async with aconn.cursor() as acur:
                async with RandomSource(artificial_delay=fake_delay) as d_source:
                    phase_one = []
                    # phase_one.append(self.do_listening(aconn, acur))
                    # phase_one.append(self.setup_data_table(aconn, acur))
                    await asyncio.gather(*phase_one)
                    phase_two = []
                    phase_two.append(self.add_data(aconn, acur, d_source, timeout=timeout))
                    await asyncio.gather(*phase_two)
        print("run complete!")

    async def run_frontend(self):
        if self.listen_channels != []:
            aconn = await psycopg.AsyncConnection.connect(conninfo=self.db_uri, autocommit=True)
            async with aconn:
                async with aconn.cursor() as acur:
                    phase_one = []
                    phase_one.append(self.new_listening(aconn, acur))
                    # phase_one.append(self.do_listening(aconn, acur))
                    await asyncio.gather(*phase_one)
        else:
            print("No channels to listen to.")

    async def add_data(self, conn: psycopg.AsyncConnection, cur: psycopg.AsyncCursor, d_source: RandomSource, timeout: float = 0):
        print("adding new data")
        loop = asyncio.get_running_loop()
        if timeout > 0:
            end_time = loop.time() + timeout
        else:
            end_time = float("inf")

        first_loop: bool = True
        first_row: int = 0
        while loop.time() < end_time:
            data = await d_source.get()
            await cur.execute(f"INSERT INTO {self.tbl_name}(ts, val) VALUES (%(ts)s, %(val)s) RETURNING id", {"ts": data[0], "val": data[1]})
            if first_loop:
                first_row = (await cur.fetchone())[0]
                first_loop = False
                print(f"{first_row=}")
                await cur.execute(f"INSERT INTO {self.tbl_name}_events(start_id) VALUES (%(start_id)s) RETURNING id", {"start_id": first_row})
                this_chunk_id = (await cur.fetchone())[0]
            await conn.commit()
        last_row = (await cur.fetchone())[0]
        print(f"{last_row=}")
        command = f"UPDATE {self.tbl_name}_events SET end_id = %(end_id)s WHERE id = %(id)s"
        data = {"id": this_chunk_id, "end_id": last_row}
        await cur.execute(command, data)
        await conn.commit()

    async def setup_data_table(self, conn: psycopg.AsyncConnection, cur: psycopg.AsyncCursor, recreate_tables: bool = False):
        if recreate_tables:
            # drop and creation order matters because of intertable refs (could probably just use CASCADE)
            await cur.execute(f"DROP TABLE IF EXISTS {self.tbl_name}_events")
            await cur.execute(f"DROP TABLE IF EXISTS {self.tbl_name}")
            await cur.execute(f"CREATE TABLE {self.tbl_name} (id bigserial PRIMARY KEY, ts timestamptz, val real)")
            await cur.execute(f"CREATE TABLE {self.tbl_name}_events (id serial PRIMARY KEY, start_id bigint, end_id bigint)")
            await cur.execute(f'ALTER TABLE "{self.tbl_name}_events" ADD FOREIGN KEY ("start_id") REFERENCES "{self.tbl_name}" ("id");')
            await cur.execute(f'ALTER TABLE "{self.tbl_name}_events" ADD FOREIGN KEY ("end_id") REFERENCES "{self.tbl_name}" ("id");')

        # (re)setup trigger & function, orders matter because of function/trigger dependance
        await cur.execute(f"DROP TRIGGER IF EXISTS {self.tbl_name}_events_changed ON {self.tbl_name}_events")
        await cur.execute(f"DROP TRIGGER IF EXISTS {self.tbl_name}_changed ON {self.tbl_name}")

        await cur.execute(f"DROP FUNCTION IF EXISTS notify_of_change_verbose()")
        await cur.execute(f"DROP FUNCTION IF EXISTS notify_of_change()")
        await cur.execute(f"CREATE FUNCTION notify_of_change_verbose() RETURNS TRIGGER AS $$ BEGIN PERFORM pg_notify(TG_ARGV[0], NEW::text); RETURN NULL; END; $$ LANGUAGE plpgsql;")
        await cur.execute(f"CREATE FUNCTION notify_of_change() RETURNS TRIGGER AS $$ BEGIN PERFORM pg_notify(TG_ARGV[0], NEW.id::text); RETURN NULL; END; $$ LANGUAGE plpgsql;")

        await cur.execute(f"CREATE TRIGGER {self.tbl_name}_events_changed AFTER INSERT OR UPDATE ON {self.tbl_name}_events FOR EACH ROW EXECUTE FUNCTION notify_of_change_verbose ('{self.tbl_name}_events')")
        await cur.execute(f"CREATE TRIGGER {self.tbl_name}_changed AFTER INSERT OR UPDATE ON {self.tbl_name} FOR EACH ROW EXECUTE FUNCTION notify_of_change ('{self.tbl_name}')")
        await conn.commit()
        print("Setup complete!")

    async def new_listening(self, conn: psycopg.AsyncConnection, cur: psycopg.AsyncCursor):
        if self.listen_channels != []:
            await asyncio.gather(*[cur.execute(f"LISTEN {ch}") for ch in self.listen_channels])
            await conn.commit()

            gen = conn.notifies()
            async for notify in gen:
                try:
                    jayson = json.loads(notify.payload)
                    jayson["channel"] = notify.channel
                    self.outq.put_nowait(jayson)
                except:
                    print(f"Failed to parse payload")
        else:
            print("No channels to listen to.")

    async def do_listening(self, conn: psycopg.AsyncConnection, cur: psycopg.AsyncCursor):
        # register listeners
        await asyncio.gather(*[cur.execute(f"LISTEN {ch}") for ch in self.listen_channels])
        await conn.commit()

        # we can now check for live running events and hook into them in real time
        for tbl in self.listen_channels:
            await cur.execute(f"SELECT start_id,end_id FROM {tbl} ORDER BY id DESC LIMIT 1")
            latest_row = await cur.fetchone()
            if latest_row[1] == None:
                # we joined while insertions are ongoing
                # so we should subscribe to it
                await cur.execute(f"LISTEN {tbl.rstrip('_events')}")
                await conn.commit()
                expecting = latest_row[0]  # this causes a prefetch of the entire history of this event
            else:
                expecting = 0

        last_one = float("inf")
        gen = conn.notifies()
        async for notify in gen:
            # print(notify)
            if notify.payload == "stop":
                break
            else:
                if notify.channel == self.tbl_name:  # raw data channel
                    # data notification, non-verbose
                    if expecting != 0:
                        command = f"SELECT * FROM {self.tbl_name} WHERE id >= %(expecting)s"
                        data = {"expecting": expecting}
                        await cur.execute(command, data)
                        async for record in cur:
                            self.outq.put_nowait(record)
                            # print(record)
                            expecting = record[0] + 1  # we expect one more than the last we got
                    else:
                        print(f"got unexpected data notification: {notify}")
                    if expecting > last_one:  # true when the block is complete
                        expecting = 0
                        last_one = float("inf")
                        await cur.execute(f"UNLISTEN {notify.channel}")
                        await conn.commit()
                elif notify.channel == f"{self.tbl_name}_events":
                    # start/stop notification
                    vals = [int(x) for x in notify.payload.strip("(),").split(",")]  # 0=this_id, 1=first_id, 2=last_id
                    if len(vals) == 1:  # non-verbose modification event
                        pass  # TODO: handle non-verbose notification: fetching the row and inspect it, then redefine vals to be 2 or three items long based on reading
                    if len(vals) == 2:  # verbose start event
                        await cur.execute(f"LISTEN {notify.channel.rstrip('_events')}")
                        await conn.commit()
                        expecting = vals[1]
                        last_one = float("inf")
                    elif len(vals) == 3:  # verbose stop event
                        last_one = vals[2]


def mainb():
    dbw = DBTool()
    asyncio.run(dbw.run_backend(fake_delay=0.01))


def mainf():
    # dbw = DBTool(db_uri="postgresql://grey@10.45.0.216/labuser")
    # dbw = DBTool(db_uri="postgresql://grey@10.56.0.4/labuser")
    # dbw = DBTool(db_uri="postgresql://grey@10.56.0.4/labuser?options=-c%20search_path%3org_greyltc")
    dbw = DBTool(db_uri="postgresql://grey@localhost/grey")
    asyncio.run(dbw.run_frontend())


if __name__ == "__main__":
    mainf()
