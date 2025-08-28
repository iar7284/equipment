from flask import Flask, redirect, url_for
from .equipment import equipment_bp

def register_routes(app: Flask):
    app.register_blueprint(equipment_bp)

    @app.route("/")
    def index():
        return redirect(url_for("equipment.list"))
