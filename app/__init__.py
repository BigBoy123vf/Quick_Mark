import os

from flask import Flask, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from . import models
from .config import Config, running_in_production
from .extensions import csrf, database, limiter, login_manager, migrate, oauth


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if running_in_production():
        # Railway terminates HTTPS at its edge and forwards plain HTTP
        # internally. Without this, url_for(_external=True) builds http://
        # links (e.g. the Google OAuth callback), which Google rejects as a
        # redirect_uri mismatch against the registered https:// URI. Also
        # trust the real client IP, since it's used for rate limiting and
        # anomaly logging.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_for=1)

    database.init_app(app)
    migrate.init_app(app, database)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    oauth.init_app(app)
    oauth.register(
        "google",
        client_id=app.config.get("GOOGLE_CLIENT_ID"),
        client_secret=app.config.get("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    from .blueprints.anomalies import anomalies_bp
    from .blueprints.auth import auth_bp
    from .blueprints.courses import courses_bp
    from .blueprints.main import main_bp
    from .blueprints.review import review_bp
    from .blueprints.scan import scan_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(courses_bp)
    app.register_blueprint(scan_bp)
    app.register_blueprint(anomalies_bp)
    app.register_blueprint(review_bp)

    app.add_template_global(static_with_version, "static_v")
    register_nav_context(app)
    register_next_class_context(app)

    # Schema is managed by migrations: flask db upgrade (dev and production).
    return app


def register_nav_context(app):
    from flask_login import current_user

    from .attendance import count_anomalies
    from .stats import count_low_attendance_students

    @app.context_processor
    def inject_nav_counts():
        if current_user.is_authenticated and current_user.role == "admin":
            return {
                "nav_anomaly_count": count_anomalies(current_user.id),
                "nav_low_attendance_count": count_low_attendance_students(current_user.id),
            }
        return {"nav_anomaly_count": 0, "nav_low_attendance_count": 0}


def register_next_class_context(app):
    from flask_login import current_user

    from .schedule import next_class_for_student, next_class_relative_label

    @app.context_processor
    def inject_next_class():
        if current_user.is_authenticated and current_user.role == "student" and current_user.index_number:
            next_class = next_class_for_student(current_user)
            if next_class:
                return {"next_class": next_class, "next_class_label": next_class_relative_label(next_class["when"])}
        return {"next_class": None, "next_class_label": None}


def static_with_version(filename):
    # Appends the file's mtime so a CSS/JS rebuild invalidates cached copies.
    url = url_for("static", filename=filename)
    full_path = os.path.join(current_app_static_root(), filename)
    try:
        version = int(os.path.getmtime(full_path))
    except OSError:
        return url
    return f"{url}?v={version}"


def current_app_static_root():
    from flask import current_app

    return current_app.static_folder


@login_manager.user_loader
def load_user(user_id):
    return models.User.query.get(int(user_id))
