import os
from pathlib import Path

from flask import Flask

from .db import init_app as init_db_app
from .routes import bp


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("CCF_DASHBOARD_SECRET", "dev-only-change-me"),
        DATABASE=str(Path(app.instance_path) / "ccf_dashboard.sqlite3"),
        STAGING_DIR=str(Path(app.instance_path) / "staged_imports"),
        MAX_CONTENT_LENGTH=32 * 1024 * 1024,
    )

    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["STAGING_DIR"]).mkdir(parents=True, exist_ok=True)

    init_db_app(app)
    app.register_blueprint(bp)
    return app

