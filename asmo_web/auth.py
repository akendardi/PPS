import re
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db

auth_bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9]{4,20}$")


@auth_bp.get("/register")
def register_get():
    return render_template("register.html")


@auth_bp.post("/register")
def register_post():
    username = request.form.get("username")
    email = request.form.get("email")
    password = request.form.get("password")

    if not USERNAME_RE.match(username):
        flash("Некорректный логин")
        return redirect("/register")

    db = get_db()

    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO users (username,email,password_hash) VALUES (%s,%s,%s)",
            (username, email, generate_password_hash(password)),
        )

    db.commit()

    return redirect("/login")


@auth_bp.get("/login")
def login_get():
    return render_template("login.html")


@auth_bp.post("/login")
def login_post():
    username = request.form.get("username")
    password = request.form.get("password")

    db = get_db()

    with db.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()

    if not user:
        flash("Пользователь не найден")
        return redirect("/login")

    if not check_password_hash(user["password_hash"], password):
        flash("Неверный пароль")
        return redirect("/login")

    session["user_id"] = user["id"]
    session["username"] = user["username"]

    return redirect("/dashboard")


@auth_bp.get("/logout")
def logout():
    session.clear()
    return redirect("/")