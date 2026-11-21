from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session


@contextmanager
def write_transaction(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session, session.begin():
        # Acquire SQLite's writer lock before reading state used in any decision.
        session.execute(text("BEGIN IMMEDIATE"))
        yield session
