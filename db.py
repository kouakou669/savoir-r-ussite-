import sqlite3
from pathlib import Path
from flask import g, current_app


def get_db() -> sqlite3.Connection:
    """Retourne une connexion SQLite par requête (stockée dans flask.g)."""
    if 'db' not in g:
        db_path = Path(current_app.instance_path) / current_app.config.get('DATABASE', 'savoir_reussite.sqlite')
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # Assure les clés étrangères
        conn.execute('PRAGMA foreign_keys = ON;')
        g.db = conn
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    schema_path = Path(current_app.root_path) / 'schema.sql'
    db.executescript(schema_path.read_text(encoding='utf-8'))
    db.commit()


def query_one(sql: str, params=()):
    cur = get_db().execute(sql, params)
    row = cur.fetchone()
    cur.close()
    return row


def query_all(sql: str, params=()):
    cur = get_db().execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def execute(sql: str, params=()):
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    last_id = cur.lastrowid
    cur.close()
    return last_id
