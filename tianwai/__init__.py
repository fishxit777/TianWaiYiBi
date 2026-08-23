import os
from pathlib import Path

from flask import Flask, jsonify

from . import db
from .security import add_security_headers, get_public_csrf_token, security_preflight


def create_app(test_config=None):
    project_root = Path(__file__).resolve().parent.parent
    production = os.environ.get("APP_ENV", "development").strip().lower() == "production"
    configured_database = os.environ.get("DATABASE_PATH", "").strip()
    database_path = Path(configured_database).expanduser() if configured_database else project_root / "data" / "tianwai.db"
    secure_public_cookie = production or os.environ.get("COOKIE_SECURE", "").strip().lower() in {
        "1", "true", "yes", "on"
    }
    app = Flask(
        __name__,
        template_folder=str(project_root / "templates"),
        static_folder=str(project_root / "static"),
    )
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("APP_SECRET_KEY", ""),
        DATABASE=str(database_path.resolve()),
        MAX_CONTENT_LENGTH=64 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=secure_public_cookie,
        LINE_ADD_FRIEND_URL=(
            os.environ.get("LINE_ADD_FRIEND_URL", "").strip()
            or "https://line.me/R/ti/p/%40279plitu"
        ),
    )
    if test_config:
        app.config.update(test_config)

    if not app.config["SECRET_KEY"]:
        if app.config.get("TESTING"):
            app.config["SECRET_KEY"] = "testing-only-secret"
        else:
            raise RuntimeError("APP_SECRET_KEY 尚未設定；請使用 run_local.ps1 啟動")
    if not app.config.get("TESTING") and len(str(app.config["SECRET_KEY"])) < 32:
        raise RuntimeError("APP_SECRET_KEY 至少需要 32 個字元（256-bit 等級）")

    db.init_app(app)
    with app.app_context():
        db.init_db()

    from .admin import admin_bp
    from .access import access_bp
    from .line_bot import line_bp
    from .payments import payments_bp
    from .public import public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(access_bp)
    app.register_blueprint(line_bp)
    app.register_blueprint(admin_bp)

    app.before_request(security_preflight)
    app.after_request(add_security_headers)

    @app.context_processor
    def inject_globals():
        return {
            "csrf_token": get_public_csrf_token,
            "line_add_friend_url": app.config["LINE_ADD_FRIEND_URL"],
        }

    @app.get("/healthz")
    def healthz():
        db.get_db().execute("SELECT 1").fetchone()
        return jsonify(
            {
                "status": "ok",
                "service": "tianwai-yibi-xiance",
                "release": "professional-ui-v16",
            }
        )

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": "找不到此頁"}), 404

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify({"error": "請求內容過大"}), 413

    return app
