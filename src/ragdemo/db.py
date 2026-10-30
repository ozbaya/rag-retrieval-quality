import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from .settings import env


def connect(dict_rows: bool = False) -> psycopg.Connection:
    # prepare_threshold=None: no server-side prepared statements (safe with Supabase poolers)
    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True, prepare_threshold=None,
                           row_factory=dict_row if dict_rows else psycopg.rows.tuple_row)
    register_vector(conn)
    return conn
