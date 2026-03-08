
from flask import Blueprint, render_template, session, redirect, url_for, request, flash

from asmo_web.db import get_db
from pricing import OptionInputs, bs_call_put, greeks
main_bp = Blueprint("main", __name__)


def login_required(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login_get"))
        return fn(*args, **kwargs)

    return wrapper


@main_bp.get("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login_get"))


@main_bp.get("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


@main_bp.get("/option")
@login_required
def option_page_get():
    return render_template("option.html", result=None, form=None)

@main_bp.post("/option")
@login_required
def option_page_post():
    def f(name, default):
        v = request.form.get(name, str(default)).strip().replace(",", ".")
        return float(v)

    try:
        form = {
            "S": request.form.get("S", "100"),
            "K": request.form.get("K", "100"),
            "T": request.form.get("T", "1"),
            "r": request.form.get("r", "0.1"),
            "sigma": request.form.get("sigma", "0.3"),
        }

        inp = OptionInputs(
            S=f("S", 100),
            K=f("K", 100),
            T=f("T", 1),
            r=f("r", 0.1),
            sigma=f("sigma", 0.3),
        )

        # простая валидация
        if inp.S <= 0 or inp.K <= 0 or inp.T <= 0 or inp.sigma <= 0:
            raise ValueError("S, K, T, sigma должны быть > 0")

        call, put = bs_call_put(inp)
        g = greeks(inp)

        result = {
            "call": call,
            "put": put,
            **g
        }
        db = get_db()
        with db.cursor() as cur:
            cur.execute("""
                        INSERT INTO option_calculations (user_id, s, k, t, r, sigma,
                                                         call_price, put_price,
                                                         delta_call, delta_put, gamma, vega,
                                                         theta_call, theta_put, rho_call, rho_put)
                        VALUES (%s, %s, %s, %s, %s, %s,
                                %s, %s,
                                %s, %s, %s, %s,
                                %s, %s, %s, %s);
                        """, (
                            session["user_id"], inp.S, inp.K, inp.T, inp.r, inp.sigma,
                            float(result["call"]), float(result["put"]),
                            float(result["delta_call"]), float(result["delta_put"]), float(result["gamma"]),
                            float(result["vega"]),
                            float(result["theta_call"]), float(result["theta_put"]), float(result["rho_call"]),
                            float(result["rho_put"])
                        ))
        db.commit()
        return render_template("option.html", result=result, form=form)

    except Exception as e:
        flash(f"Ошибка ввода/расчёта: {e}", "error")
        return redirect(url_for("main.option_page_get"))


@main_bp.get("/volatility")
@login_required
def volatility_page():
    return render_template("volatility.html")


@main_bp.get("/reports")
@login_required
def reports_page():
    db = get_db()
    with db.cursor() as cur:
        cur.execute("""
            SELECT id, created_at, s, k, t, r, sigma, call_price, put_price
            FROM option_calculations
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 50;
        """, (session["user_id"],))
        rows = cur.fetchall()

    return render_template("reports.html", rows=rows)


@main_bp.get("/reset")
def reset_page():
    return "Заглушка: сброс пароля (можно сделать позже)"