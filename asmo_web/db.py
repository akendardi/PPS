import psycopg
from psycopg.rows import dict_row
from flask import g
from .config import Config


def get_db():
    if "db" not in g:
        g.db = psycopg.connect(
            Config.DATABASE_URL,
            row_factory=dict_row
        )
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()

    with db.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                login VARCHAR(20) UNIQUE NOT NULL,
                email VARCHAR(50) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'analyst'
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS option_calculations (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                ticker VARCHAR(20),
                interval_code VARCHAR(20),
                s DOUBLE PRECISION NOT NULL,
                k DOUBLE PRECISION NOT NULL,
                t DOUBLE PRECISION NOT NULL,
                r DOUBLE PRECISION NOT NULL,
                sigma DOUBLE PRECISION NOT NULL,
                call_price DOUBLE PRECISION NOT NULL,
                put_price DOUBLE PRECISION NOT NULL,
                delta_call DOUBLE PRECISION,
                delta_put DOUBLE PRECISION,
                gamma DOUBLE PRECISION,
                vega DOUBLE PRECISION,
                theta_call DOUBLE PRECISION,
                theta_put DOUBLE PRECISION,
                rho_call DOUBLE PRECISION,
                rho_put DOUBLE PRECISION,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS volatility_reports (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                ticker VARCHAR(20) NOT NULL,
                instrument_name VARCHAR(120) NOT NULL,
                horizon_code VARCHAR(10) NOT NULL,
                current_iv DOUBLE PRECISION NOT NULL,
                predicted_iv DOUBLE PRECISION NOT NULL,
                lower_bound DOUBLE PRECISION NOT NULL,
                upper_bound DOUBLE PRECISION NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        db.commit()