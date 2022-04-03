import psycopg
import getpass
import asyncio


class DBWriter(object):
    db_proto = "postgresql://"
    db_user = None
    db_name = None
    db_host = None
    db_port = 5432
    db_uri = None
    listen_channels = []

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

    async def run(self):
        aconn = await psycopg.AsyncConnection.connect(conninfo=self.db_uri, autocommit=True)
        async with aconn:
            async with aconn.cursor() as cur:
                await asyncio.gather(*[cur.execute(f"LISTEN {ch}") for ch in self.listen_channels])
                gen = aconn.notifies()
                async for notify in gen:
                    print(notify)
                    if notify.payload == "stop":
                        break
                print("there, I stopped")


def main():
    dbw = DBWriter(db_name="grey")
    dbw.listen_channels.append("doink")
    asyncio.run(dbw.run())


if __name__ == "__main__":
    main()
