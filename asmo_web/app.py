from flask import Flask
from config import Config
from db import close_db, init_db
from auth import auth_bp
from views import main_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    app.teardown_appcontext(close_db)

    @app.cli.command("init-db")
    def init_db_command():
        init_db()
        print("DB initialized")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)