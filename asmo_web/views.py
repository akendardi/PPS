from functools import wraps
import json
import base64
import pandas as pd

from flask import Blueprint, render_template, session, redirect, url_for, request, flash, send_file, abort

from .db import get_db
from .pricing import OptionInputs, bs_call_put, greeks
from .market_data import (
    search_instruments,
    build_option_snapshot,
    get_intervals,
    get_instrument_name,
    get_interval_label,
)
from .charts import build_all_charts, build_chart_buffers
from .pdf_report import build_pdf
from .vol_model import train_vol_bundle, predict_vol_for_ticker, make_vol_forecast_chart

main_bp = Blueprint("main", __name__)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return fn(*args, **kwargs)
    return wrapper


def format_dt(dt_value):
    if not dt_value:
        return ""
    ts = pd.to_datetime(dt_value, errors="coerce")
    if pd.isna(ts):
        return str(dt_value)
    return ts.strftime("%d.%m.%Y %H:%M")


def row_to_snapshot(row):
    return {
        "ticker": row["ticker"],
        "instrument_name": get_instrument_name(row["ticker"]),
        "interval_code": row.get("interval_code") or "30d",
        "interval_label": get_interval_label(row.get("interval_code") or "30d"),
        "S": float(row["s"]),
        "K": float(row["k"]),
        "T": float(row["t"]),
        "r": float(row["r"]),
        "sigma": float(row["sigma"]),
    }


def result_to_forecast_rows(result):
    rows = []
    for _, row in result["forecast_table"].iterrows():
        rows.append({
            "date": pd.to_datetime(row["DATE"]).strftime("%d.%m.%Y"),
            "iv_fact": None if pd.isna(row["IV_FACT"]) else float(row["IV_FACT"]),
            "iv_forecast": None if pd.isna(row["IV_FORECAST"]) else float(row["IV_FORECAST"]),
            "lower": None if pd.isna(row["LOWER"]) else float(row["LOWER"]),
            "upper": None if pd.isna(row["UPPER"]) else float(row["UPPER"]),
        })
    return rows


@main_bp.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@main_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


@main_bp.route("/option-menu")
@login_required
def option_menu():
    query = request.args.get("q", "").strip()
    items = search_instruments(query)
    return render_template("option_menu.html", items=items, query=query)


@main_bp.route("/volatility-menu")
@login_required
def volatility_menu():
    query = request.args.get("q", "").strip()
    items = search_instruments(query)
    return render_template("volatility_menu.html", items=items, query=query)


@main_bp.route("/option", methods=["GET", "POST"])
@login_required
def option():
    ticker = request.args.get("ticker", "").strip().upper() or request.form.get("ticker", "").strip().upper()

    if request.method == "POST":
        interval_code = request.form.get("interval_code", "30d")
    else:
        interval_code = request.args.get("interval", "30d")

    result = None
    snapshot = None
    charts = None
    last_report_id = None
    intervals = get_intervals()

    if not ticker:
        flash("Сначала выберите инструмент", "error")
        return redirect(url_for("main.option_menu"))

    if request.method == "POST":
        try:
            snapshot = build_option_snapshot(ticker, interval_code)

            inp = OptionInputs(
                S=snapshot["S"],
                K=snapshot["K"],
                T=snapshot["T"],
                r=snapshot["r"],
                sigma=snapshot["sigma"],
            )

            call_price, put_price = bs_call_put(inp)
            g = greeks(inp)

            result = {
                "call": round(float(call_price), 6),
                "put": round(float(put_price), 6),
                "delta_call": round(float(g["delta_call"]), 6),
                "delta_put": round(float(g["delta_put"]), 6),
                "gamma": round(float(g["gamma"]), 6),
                "vega": round(float(g["vega"]), 6),
                "theta_call": round(float(g["theta_call"]), 6),
                "theta_put": round(float(g["theta_put"]), 6),
                "rho_call": round(float(g["rho_call"]), 6),
                "rho_put": round(float(g["rho_put"]), 6),
            }

            charts = build_all_charts(snapshot)

            db = get_db()
            with db.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO option_calculations (
                        user_id,
                        ticker,
                        interval_code,
                        s,
                        k,
                        t,
                        r,
                        sigma,
                        call_price,
                        put_price,
                        delta_call,
                        delta_put,
                        gamma,
                        vega,
                        theta_call,
                        theta_put,
                        rho_call,
                        rho_put
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING id
                    """,
                    (
                        session["user_id"],
                        snapshot["ticker"],
                        interval_code,
                        snapshot["S"],
                        snapshot["K"],
                        snapshot["T"],
                        snapshot["r"],
                        snapshot["sigma"],
                        result["call"],
                        result["put"],
                        result["delta_call"],
                        result["delta_put"],
                        result["gamma"],
                        result["vega"],
                        result["theta_call"],
                        result["theta_put"],
                        result["rho_call"],
                        result["rho_put"],
                    ),
                )
                inserted = cur.fetchone()
                last_report_id = inserted["id"]
                db.commit()

            flash("Расчёт выполнен успешно. Отчёт сохранён.", "success")

        except Exception as e:
            flash(f"Ошибка загрузки данных или расчёта: {e}", "error")

    return render_template(
        "option.html",
        ticker=ticker,
        interval_code=interval_code,
        intervals=intervals,
        snapshot=snapshot,
        result=result,
        charts=charts,
        last_report_id=last_report_id,
        get_interval_label=get_interval_label,
    )


@main_bp.route("/volatility", methods=["GET", "POST"])
@login_required
def volatility():
    ticker = request.args.get("ticker", "").strip().upper() or request.form.get("ticker", "").strip().upper()

    if not ticker and request.method == "GET":
        return redirect(url_for("main.volatility_menu"))

    horizon_code = request.form.get("horizon_code", request.args.get("horizon", "7d"))

    prediction = None
    chart = None
    instrument_name = ticker
    current_hv20 = None
    lower = None
    upper = None
    horizon_label = None
    forecast_rows = None

    if request.method == "POST":
        try:
            train_vol_bundle(horizon_code=horizon_code, force=False)
            result = predict_vol_for_ticker(ticker, horizon_code=horizon_code)
            chart = make_vol_forecast_chart(result)

            prediction = result["prediction"]
            current_hv20 = result["current_hv20"]
            lower = result["lower"]
            upper = result["upper"]
            instrument_name = result["instrument_name"]
            horizon_label = f"{result['horizon_days']} дн."
            forecast_rows = result_to_forecast_rows(result)

            flash("Прогноз волатильности выполнен успешно", "success")

        except Exception as e:
            flash(f"Ошибка прогноза: {e}", "error")

    return render_template(
        "volatility.html",
        ticker=ticker,
        instrument_name=instrument_name,
        horizon_code=horizon_code,
        horizon_label=horizon_label,
        prediction=prediction,
        current_hv20=current_hv20,
        lower=lower,
        upper=upper,
        chart=chart,
        forecast_rows=forecast_rows,
    )


@main_bp.route("/volatility/save", methods=["POST"])
@login_required
def save_volatility_report():
    ticker = request.form.get("ticker", "").strip().upper()
    instrument_name = request.form.get("instrument_name", "").strip()
    horizon_code = request.form.get("horizon_code", "").strip()
    current_iv = request.form.get("current_iv", "").strip()
    predicted_iv = request.form.get("predicted_iv", "").strip()
    lower_bound = request.form.get("lower_bound", "").strip()
    upper_bound = request.form.get("upper_bound", "").strip()
    forecast_rows_json = request.form.get("forecast_rows_json", "").strip()
    chart_base64 = request.form.get("chart_base64", "").strip()

    if not all([ticker, instrument_name, horizon_code, current_iv, predicted_iv, lower_bound, upper_bound]):
        flash("Не удалось сохранить прогноз: не хватает данных", "error")
        return redirect(url_for("main.volatility", ticker=ticker, horizon=horizon_code))

    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO volatility_reports (
                user_id,
                ticker,
                instrument_name,
                horizon_code,
                current_iv,
                predicted_iv,
                lower_bound,
                upper_bound,
                forecast_table_json,
                chart_base64
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session["user_id"],
                ticker,
                instrument_name,
                horizon_code,
                float(current_iv),
                float(predicted_iv),
                float(lower_bound),
                float(upper_bound),
                forecast_rows_json or "[]",
                chart_base64 or None,
            ),
        )
    db.commit()

    flash("Прогноз сохранён в архив", "success")
    return redirect(url_for("main.reports"))


@main_bp.route("/reports")
@login_required
def reports():
    db = get_db()

    option_items = []
    volatility_items = []

    with db.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                ticker,
                interval_code,
                created_at
            FROM option_calculations
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 100
            """,
            (session["user_id"],)
        )
        option_rows = cur.fetchall()

        cur.execute(
            """
            SELECT
                id,
                ticker,
                instrument_name,
                horizon_code,
                predicted_iv,
                created_at
            FROM volatility_reports
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 100
            """,
            (session["user_id"],)
        )
        volatility_rows = cur.fetchall()

    for row in option_rows:
        option_items.append({
            "id": row["id"],
            "type": "option",
            "title": f"Отчет {row['id']}",
            "instrument": row["ticker"],
            "subtitle": f"Инструмент: {row['ticker']}",
            "created_at": format_dt(row["created_at"]),
        })

    for row in volatility_rows:
        volatility_items.append({
            "id": row["id"],
            "type": "volatility",
            "title": f"Отчет {row['id']}",
            "instrument": row["ticker"],
            "subtitle": f"Инструмент: {row['instrument_name']} ({row['ticker']})",
            "created_at": format_dt(row["created_at"]),
        })

    rows = option_items + volatility_items
    rows.sort(key=lambda x: x["created_at"], reverse=True)

    return render_template("reports.html", rows=rows)


@main_bp.route("/reports/<report_type>/<int:report_id>")
@login_required
def report_detail_unified(report_type, report_id):
    db = get_db()

    if report_type == "option":
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM option_calculations
                WHERE id = %s AND user_id = %s
                """,
                (report_id, session["user_id"]),
            )
            row = cur.fetchone()

        if not row:
            abort(404)

        snapshot = row_to_snapshot(row)
        result = {
            "call": row["call_price"],
            "put": row["put_price"],
            "delta_call": row["delta_call"],
            "delta_put": row["delta_put"],
            "gamma": row["gamma"],
            "vega": row["vega"],
            "theta_call": row["theta_call"],
            "theta_put": row["theta_put"],
            "rho_call": row["rho_call"],
            "rho_put": row["rho_put"],
        }

        # Для HTML-отчёта используем тот же способ, что и на основной странице расчёта
        charts = build_all_charts(snapshot)

        return render_template(
            "report_detail.html",
            report=row,
            snapshot=snapshot,
            result=result,
            charts=charts,
            format_dt=format_dt,
        )

    if report_type == "volatility":
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM volatility_reports
                WHERE id = %s AND user_id = %s
                """,
                (report_id, session["user_id"]),
            )
            row = cur.fetchone()

        if not row:
            abort(404)

        forecast_rows = json.loads(row["forecast_table_json"] or "[]")

        return render_template(
            "volatility_report_detail.html",
            report=row,
            forecast_rows=forecast_rows,
            format_dt=format_dt,
        )

    abort(404)


@main_bp.route("/reports/<int:report_id>/pdf")
@login_required
def report_pdf(report_id):
    db = get_db()

    with db.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM option_calculations
            WHERE id = %s AND user_id = %s
            """,
            (report_id, session["user_id"]),
        )
        row = cur.fetchone()

    if not row:
        abort(404)

    snapshot = row_to_snapshot(row)
    graph_buffers = build_chart_buffers(snapshot)

    report_data = {
        "id": row["id"],
        "ticker": row["ticker"],
        "instrument_name": snapshot["instrument_name"],
        "interval_label": snapshot["interval_label"],
        "created_at": str(row["created_at"]),
        "S": row["s"],
        "K": row["k"],
        "T": row["t"],
        "r": row["r"],
        "sigma": row["sigma"],
        "call_price": row["call_price"],
        "put_price": row["put_price"],
        "delta_call": row["delta_call"],
        "delta_put": row["delta_put"],
        "gamma": row["gamma"],
        "vega": row["vega"],
        "theta_call": row["theta_call"],
        "theta_put": row["theta_put"],
        "rho_call": row["rho_call"],
        "rho_put": row["rho_put"],
    }

    pdf_buffer = build_pdf(report_data, graph_buffers)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"report_{row['ticker']}_{report_id}.pdf",
        mimetype="application/pdf",
    )


@main_bp.route("/reset")
def reset_page():
    return "Заглушка: сброс пароля (можно сделать позже)"