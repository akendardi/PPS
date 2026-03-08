import psycopg
from psycopg.rows import dict_row
from flask import g
from config import Config


def get_db():
    if "db" not in g:
        g.db = psycopg.connect(Config.DATABASE_URL, row_factory=dict_row)
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with psycopg.connect(Config.DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    username VARCHAR(20) UNIQUE NOT NULL,
                    email VARCHAR(50) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role VARCHAR(20) NOT NULL DEFAULT 'analyst',
                    created_at TIMESTAMPTZ DEFAULT now()
                );
            """)
            conn.commit()

            cur.execute("""
                        CREATE TABLE IF NOT EXISTS option_calculations
                        (
                            id
                            BIGSERIAL
                            PRIMARY
                            KEY,
                            user_id
                            BIGINT
                            NOT
                            NULL
                            REFERENCES
                            users
                        (
                            id
                        ) ON DELETE CASCADE,
    
                            s DOUBLE PRECISION NOT NULL,
                            k DOUBLE PRECISION NOT NULL,
                            t DOUBLE PRECISION NOT NULL,
                            r DOUBLE PRECISION NOT NULL,
                            sigma DOUBLE PRECISION NOT NULL,
    
                            call_price DOUBLE PRECISION NOT NULL,
                            put_price DOUBLE PRECISION NOT NULL,
    
                            delta_call DOUBLE PRECISION NOT NULL,
                            delta_put DOUBLE PRECISION NOT NULL,
                            gamma DOUBLE PRECISION NOT NULL,
                            vega DOUBLE PRECISION NOT NULL,
                            theta_call DOUBLE PRECISION NOT NULL,
                            theta_put DOUBLE PRECISION NOT NULL,
                            rho_call DOUBLE PRECISION NOT NULL,
                            rho_put DOUBLE PRECISION NOT NULL,
    
                            created_at TIMESTAMPTZ NOT NULL DEFAULT now
                        (
                        )
                            );
                        """)