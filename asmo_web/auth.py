import re
from flask import Blueprint, render_template, request, redirect, session, flash, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from .db import get_db

auth_bp = Blueprint("auth", __name__)

LOGIN_RE = re.compile(r"^[A-Za-z0-9]{4,20}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_password(password: str) -> bool:
    if not password or len(password) < 8 or len(password) > 32:
        return False

    has_upper = re.search(r"[A-Z]", password)
    has_lower = re.search(r"[a-z]", password)
    has_digit = re.search(r"\d", password)
    has_special = re.search(r"[!@#$%^&*]", password)

    return all([has_upper, has_lower, has_digit, has_special])


@auth_bp.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        login = request.form.get("login", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not login or not email or not password or not confirm_password:
            flash("Заполните все обязательные поля", "error")
            return render_template("register.html")

        if not LOGIN_RE.fullmatch(login):
            flash("Логин должен содержать 4–20 символов (латиница и цифры)", "error")
            return render_template("register.html")

        if len(email) > 50 or not EMAIL_RE.fullmatch(email):
            flash("Некорректный формат электронной почты", "error")
            return render_template("register.html")

        if not is_valid_password(password):
            flash("Пароль должен содержать минимум 8 символов, включая цифры и спецсимвол", "error")
            return render_template("register.html")

        if password != confirm_password:
            flash("Пароли не совпадают", "error")
            return render_template("register.html")

        db = get_db()

        with db.cursor() as cur:

            cur.execute(
                """
                SELECT id
                FROM users
                WHERE login = %s OR email = %s
                """,
                (login, email)
            )

            user = cur.fetchone()

            if user:
                flash("Пользователь с таким логином или email уже существует", "error")
                return render_template("register.html")

            password_hash = generate_password_hash(password)

            cur.execute(
                """
                INSERT INTO users (login, email, password_hash, role)
                VALUES (%s, %s, %s, %s)
                """,
                (login, email, password_hash, "analyst")
            )

            db.commit()

        flash("Регистрация успешно завершена", "success")

        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        login = request.form.get("login", "").strip()
        password = request.form.get("password", "")

        if not login or not password:
            flash("Введите логин и пароль", "error")
            return render_template("login.html")

        db = get_db()

        with db.cursor() as cur:

            cur.execute(
                """
                SELECT id, login, password_hash, role
                FROM users
                WHERE login = %s
                """,
                (login,)
            )

            user = cur.fetchone()

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Неверный логин или пароль", "error")
            return render_template("login.html")

        session.clear()

        session["user_id"] = user["id"]
        session["login"] = user["login"]
        session["role"] = user["role"]

        return redirect(url_for("main.dashboard"))

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("auth.login"))