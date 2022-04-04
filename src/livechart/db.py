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

    async def run_backend(self, timeout=5):
        aconn = await psycopg.AsyncConnection.connect(conninfo=self.db_uri, autocommit=True)
        async with aconn:
            async with aconn.cursor() as acur:
                async with ThermalSource(artificial_delay=0.001) as d_source:
                    phase_one = []
                    # phase_one.append(self.do_listening(aconn, acur))
                    phase_one.append(self.setup_data_table(aconn, acur))
                    await asyncio.gather(*phase_one)
                    phase_two = []
                    phase_two.append(self.add_data(aconn, acur, d_source, timeout=timeout))
                    await asyncio.gather(*phase_two)
        print("run complete!")

    async def run_frontend(self):
        self.listen_channels.append(self.tbl_name)
        aconn = await psycopg.AsyncConnection.connect(conninfo=self.db_uri, autocommit=True)
        async with aconn:
            async with aconn.cursor() as acur:
                phase_one = []
                phase_one.append(self.do_listening(aconn, acur))
                await asyncio.gather(*phase_one)

    async def add_data(self, conn: psycopg.AsyncConnection, cur: psycopg.AsyncCursor, d_source: RandomSource, timeout=None):
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        while True:
            data = await d_source.get()
            try:
                await cur.execute(f"INSERT INTO {self.tbl_name}(ts, val) VALUES (%(ts)s, %(val)s);", {"ts": data[0], "val": data[1]})
            except Exception as e:
                print(e)
            await conn.commit()
            if (timeout is not None) and (timeout > 0) and ((loop.time() - t0) > timeout):
                break

    async def setup_data_table(self, conn: psycopg.AsyncConnection, cur: psycopg.AsyncCursor):
        await cur.execute(f"DROP TABLE IF EXISTS {self.tbl_name}")
        await cur.execute(f"CREATE TABLE {self.tbl_name} (id bigserial PRIMARY KEY, ts timestamptz, val float8)")
        await cur.execute(f"CREATE OR REPLACE FUNCTION notify_of_change() RETURNS TRIGGER AS $$ BEGIN PERFORM pg_notify(TG_ARGV[0], TG_ARGV[1]); RETURN NEW; END; $$ LANGUAGE plpgsql;")

        # TODO: will go away:
        await cur.execute(f"DROP TRIGGER IF EXISTS {self.tbl_name}_changed ON {self.tbl_name}")
        await cur.execute(f"CREATE TRIGGER {self.tbl_name}_changed AFTER INSERT ON {self.tbl_name} FOR EACH STATEMENT EXECUTE FUNCTION notify_of_change ('{self.tbl_name}', 'after_insert')")

        # TODO: change to this when we get postgresql 14:
        # await cur.execute(f"CREATE OR REPLACE TRIGGER {self.tbl_name}_changed AFTER INSERT ON {self.tbl_name} FOR EACH STATEMENT EXECUTE FUNCTION notify_of_change ('{self.tbl_name}', 'after_insert')")

        await conn.commit()
        print("Table made!")

    async def do_listening(self, conn: psycopg.AsyncConnection, cur: psycopg.AsyncCursor):
        # register listeners
        await asyncio.gather(*[cur.execute(f"LISTEN {ch}") for ch in self.listen_channels])
        gen = conn.notifies()
        async for notify in gen:
            print(notify)
            if notify.payload == "stop":
                break
        print("there, I stopped")


def main():
    dbw = DBTool()
    asyncio.run(dbw.run_backend())


def main2():
    dbw = DBTool()
    asyncio.run(dbw.run_frontend())


if __name__ == "__main__":
    main()
