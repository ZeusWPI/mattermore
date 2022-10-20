from flask import Response, abort, request
from functools import wraps
import hashlib
import hmac
import json
import requests
import time
from typing import Union

from app import models
from app.app import DOOR_STATUS, mm_driver

import config


def get_mattermost_id(username: str) -> Union[str, None]:
    """
    Given a mattermost username, return the user id.

    Returns `None` if no user with the given username exists

    Don't call this with stale data
    """

    try:
        response = mm_driver.users.get_user_by_username(username)
        return response["id"]
    except:
        return None


def query_and_update_username() -> "models.User":
    """Updates mattermost data if need be. Only use in requests."""

    mattermost_user_id = request.values.get("user_id")
    username = request.values.get("user_name")
    user = models.User.find_by_mm_id(mattermost_user_id)
    if not user:
        return None
    if user.username != username:
        user.username = username
        user.save()
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


def requires_token(token_name: str):
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


def mattermost_response(message: str, ephemeral: bool = False) -> Response:
    """Reply to a message in the same channel, optionally making the message ephemeral"""

    response_dict = {
        "response_type": "ephemeral" if ephemeral else "in_channel",
        "text": message,
    }
    return Response(json.dumps(response_dict), mimetype="application/json")


def mattermost_doorkeeper_message(
    message: str, webhook: str = config.doorkeeper_webhook
) -> "requests.Response":
    """Send a message to the doorkeeper channel, or some other custom webhook"""

    requests.post(webhook, json={"text": message})


def get_actual_username(username: str) -> str:
    """Removes @ from username if @ was prepended"""

    return username.lstrip("@")


def lockbot_request(command: str) -> str:
    """
    Send a command to lockbot, returns the status of the door after the request
    was handled
    """

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
