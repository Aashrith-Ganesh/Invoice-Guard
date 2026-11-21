import sqlite3

from sqlalchemy import Engine, create_engine, event


def make_engine(url: str) -> Engine:
    engine = create_engine(url, hide_parameters=True, connect_args={"timeout": 20})

    @event.listens_for(engine, "connect")
    def configure(connection: sqlite3.Connection, _) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    return engine
