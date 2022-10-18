from flask import Flask, request, Response, abort, render_template, send_file, jsonify
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
import hashlib
import hmac
import json
from mattermostdriver import Driver
import re
import requests
import time

import config
from routes import (
    cammie_blueprint,
    door_access_blueprint,
    door_control_blueprint,
    doorkeeper_blueprint,
    fingerprint_blueprint,
    quote_blueprint,
    resto_blueprint,
    spaceapi_blueprint,
)


app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URL
# Supress Flask warning
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

app.register_blueprint(cammie_blueprint)
app.register_blueprint(door_access_blueprint)
app.register_blueprint(door_control_blueprint)
app.register_blueprint(doorkeeper_blueprint)
app.register_blueprint(fingerprint_blueprint)
app.register_blueprint(quote_blueprint)
app.register_blueprint(resto_blueprint)
app.register_blueprint(spaceapi_blueprint)

response_setting = "in_channel"

# Login driver: used to send messages to Mattermost
mm_driver = Driver(
    {"port": 443, "url": config.server_url, "token": config.mm_driver_token}
)
mm_driver.login()

DOOR_STATUS = {"0": "locked", "1": "open", "2": "inbetween"}

from app import models
from app import cron


def get_mattermost_id(username):
    """Given a mattermost username, return the user id. Don't call this with stale data"""
    try:
        response = mm_driver.users.get_user_by_username(username)
        return response["id"]
    except:
        return None


def query_and_update_username():
    """Updates mattermost data if need be. Only use in requests."""
    mattermost_user_id = request.values.get("user_id")
    username = request.values.get("user_name")
    user = models.User.query.filter_by(mattermost_id=mattermost_user_id).first()
    if not user:
        return None
    if user.username != username:
        user.username = username
        db.session.add(user)
        db.session.commit()
    return user


def requires_regular(f):
    """Decorator to require a regular user"""

    @wraps(f)
    def decorated(*args, **kwargs):
        user = query_and_update_username()
        if not user or not user.authorized:
            return abort(401)
        return f(user, *args, **kwargs)

    return decorated


def requires_admin(f):
    """Decorator to require an admin user"""

    @wraps(f)
    def decorated(*args, **kwargs):
        user = query_and_update_username()
        if not user or not user.authorized or not user.admin:
            return abort(401)
        return f(user, *args, **kwargs)

    return decorated


def requires_token(token_name):
    """Decorator to require a correct Mattermost token"""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            expected_token = config.tokens[token_name]
            token = request.values.get("token")
            if expected_token != token:
                return abort(401)
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def mattermost_response(message, ephemeral=False):
    response_dict = {
        "response_type": "ephemeral" if ephemeral else "in_channel",
        "text": message,
    }
    return Response(json.dumps(response_dict), mimetype="application/json")


def mattermost_doorkeeper_message(message, webhook=config.doorkeeper_webhook):
    requests.post(webhook, json={"text": message})


# Removes @ from username if @ was prepended
def get_actual_username(username):
    return username.lstrip("@")


def lockbot_request(command):
    # TODO: fix this properly with a mutex
    # TODO: cache status requests
    timestamp = int(time.time() * 1000)
    payload = f"{timestamp};{command}"
    calculated_hmac = (
        hmac.new(config.down_key.encode("utf8"), payload.encode("utf8"), hashlib.sha256)
        .hexdigest()
        .upper()
    )
    r = requests.post(config.lockbot_url, payload, headers={"HMAC": calculated_hmac})
    return DOOR_STATUS[r.text]


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
