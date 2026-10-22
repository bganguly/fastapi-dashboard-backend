import os
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager

_pool: ThreadedConnectionPool | None = None


def _create_pool() -> ThreadedConnectionPool:
    url = os.environ["DATABASE_URL"]
    return ThreadedConnectionPool(minconn=2, maxconn=10, dsn=url)


def get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = _create_pool()
    return _pool


@contextmanager
def get_conn():
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
