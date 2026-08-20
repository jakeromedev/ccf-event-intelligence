import os

from app import create_app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("CCF_DASHBOARD_PORT", "5050"))
    debug = os.environ.get("CCF_DASHBOARD_DEBUG", "0") == "1"
    app.run(debug=debug, host="127.0.0.1", port=port)
