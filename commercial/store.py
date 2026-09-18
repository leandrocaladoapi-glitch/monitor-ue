"""Private transactional store: PostgreSQL in production; explicit local SQLite only."""
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA = '''CREATE TABLE IF NOT EXISTS commercial_records (
 kind TEXT NOT NULL, id TEXT NOT NULL, account_id TEXT NOT NULL DEFAULT '',
 payload TEXT NOT NULL, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL,
 PRIMARY KEY (kind, id)
)'''


class Store:
    def __init__(self, conn, postgres=False):
        self.conn=conn; self.postgres=postgres
    def execute(self, sql, args=()):
        return self.conn.execute(sql.replace('?', '%s') if self.postgres else sql,args)
    def get(self,kind,key):
        row=self.execute('SELECT payload FROM commercial_records WHERE kind=? AND id=?',(kind,key)).fetchone()
        return json.loads(row[0]) if row else None
    def put(self,kind,key,data,account=''):
        now=int(time.time())
        self.execute('INSERT INTO commercial_records(kind,id,account_id,payload,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload, account_id=excluded.account_id, updated_at=excluded.updated_at',(kind,key,account,json.dumps(data,ensure_ascii=False),now,now))
    def insert(self,kind,key,data,account=''):
        now=int(time.time())
        return self.execute('INSERT INTO commercial_records(kind,id,account_id,payload,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(kind,id) DO NOTHING',(kind,key,account,json.dumps(data,ensure_ascii=False),now,now)).rowcount==1
    def list(self,kind,account=None,limit=1000):
        sql='SELECT id,payload FROM commercial_records WHERE kind=?';args=[kind]
        if account is not None:sql+=' AND account_id=?';args.append(account)
        sql+=' ORDER BY created_at,id LIMIT ?';args.append(limit)
        return [(r[0],json.loads(r[1])) for r in self.execute(sql,args).fetchall()]
    def delete(self,kind,key):
        self.execute('DELETE FROM commercial_records WHERE kind=? AND id=?',(kind,key))
    def lock(self,key):
        if self.postgres:self.execute('SELECT pg_advisory_xact_lock(hashtext(?))',(key,))
    def commit(self):self.conn.commit()


@contextmanager
def connect():
    dsn=os.environ.get('DATABASE_URL')
    if dsn:
        import psycopg
        conn=psycopg.connect(dsn,connect_timeout=10)
        s=Store(conn,True)
    elif os.environ.get('MONITOR_DEV')=='1' and not os.environ.get('VERCEL'):
        path=os.environ.get('COMMERCIAL_SQLITE','/tmp/monitor-commercial.sqlite3')
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        conn=sqlite3.connect(path,timeout=10)
        conn.execute('BEGIN IMMEDIATE')
        s=Store(conn)
    else:
        raise RuntimeError('Private database not configured')
    try:
        yield s
        conn.commit()
    except Exception:
        conn.rollback();raise
    finally:conn.close()


def configured():
    """Whether a private database is expected here (Vercel never accepts the local file)."""
    return bool(os.environ.get('DATABASE_URL') or (os.environ.get('MONITOR_DEV')=='1' and not os.environ.get('VERCEL')))


@contextmanager
def connect_optional():
    """Store for routes that can degrade to notification-only capture; None when no database is set.

    A configured-but-broken database still raises: silently dropping leads into e-mail only would
    hide an outage of the system of record.
    """
    if not configured():
        yield None
        return
    with connect() as s:
        yield s


def migrate():
    with connect() as s:
        s.execute(SCHEMA)
        s.execute('CREATE INDEX IF NOT EXISTS commercial_account_idx ON commercial_records(kind,account_id)')
