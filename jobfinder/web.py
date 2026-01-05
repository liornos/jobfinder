from flask import Blueprint, render_template

web_bp = Blueprint("web", __name__, template_folder="templates", static_folder="static")


@web_bp.get("/")
def index():
    return render_template("index.html")


@web_bp.get("/search")
def search():
    return render_template("search.html")
