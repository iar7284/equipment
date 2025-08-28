import os
from flask import Flask
from config import Config

def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)

    # Jinja helper: akses config di template
    @app.context_processor
    def inject_config():
        return {"config": app.config}

    # Register blueprints & root route (dari routes/__init__.py)
    from routes import register_routes
    register_routes(app)

    # Optional: dump routes saat start
    print("=== ROUTES ===")
    for r in app.url_map.iter_rules():
        print(r, "->", r.endpoint, r.methods)

    return app


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=port)
