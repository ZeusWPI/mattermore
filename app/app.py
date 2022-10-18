from flask import Flask, abort, render_template, send_file, jsonify
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from mattermostdriver import Driver
import re

import config


app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URL
# Supress Flask warning
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

response_setting = "in_channel"

# Login driver: used to send messages to Mattermost
mm_driver = Driver(
    {"port": 443, "url": config.server_url, "token": config.mm_driver_token}
)
mm_driver.login()

DOOR_STATUS = {"0": "locked", "1": "open", "2": "inbetween"}

from app import models
from app import cron

from app.routes import (
    cammie_blueprint,
    door_access_blueprint,
    door_control_blueprint,
    doorkeeper_blueprint,
    fingerprint_blueprint,
    quote_blueprint,
    resto_blueprint,
    spaceapi_blueprint,
)

app.register_blueprint(cammie_blueprint)
app.register_blueprint(door_access_blueprint)
app.register_blueprint(door_control_blueprint)
app.register_blueprint(doorkeeper_blueprint)
app.register_blueprint(fingerprint_blueprint)
app.register_blueprint(quote_blueprint)
app.register_blueprint(resto_blueprint)
app.register_blueprint(spaceapi_blueprint)


@app.route("/robots.txt", methods=["GET"])
def get_robots():
    return send_file("static/robots.txt")


@app.route("/fonts/<filename>", methods=["GET"])
def get_font(filename):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*\.(?:otf|svg|woff2?)", filename):
        return abort(404)

    return send_file("static/fonts/" + filename)


@app.route("/quotes.css", methods=["GET"])
def get_quote_css():
    return send_file("static/quotes.css")


@app.route("/quotes.html", methods=["GET"])
def list_quotes():
    return render_template("quotes.html", quotes=reversed(models.Quote.query.all()))


@app.route("/quotes.json", methods=["GET"])
def json_quotes():
    all_quotes = models.Quote.query.all()
    response = jsonify(
        list(
            {
                "quoter": q.quoter,
                "quotee": q.quotee,
                "channel": q.channel,
                "quote": q.quote,
                "created_at": q.created_at.isoformat(),
            }
            for q in all_quotes
        )
    )
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response
