"""SQLite 연결 의존성 (FastAPI Depends 용)."""
import sqlite3
from contextlib import contextmanager

from app.config import DB_PATH


def get_connection() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


@contextmanager
def db_session():
    con = get_connection()
    try:
        yield con
    finally:
        con.close()
