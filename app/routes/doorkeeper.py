from flask import Blueprint, abort, request
import hashlib
import hmac
import requests
import sys
import traceback
from datetime import datetime, timedelta


from app.app import DOOR_STATUS
from app.util import (
    mattermost_doorkeeper_message,
    mark_door_electronically_used,
    in_electronic_action_period,
    get_persistent_kv
)

import config

KV_KEY_KELDERAPI_LAST_ERROR_MESSAGE = "kelderapi_last_error_message"
KV_KEY_KELDERAPI_ERROR_COUNT = "kelderapi_error_count"

doorkeeper_blueprint = Blueprint("doorkeeper", __name__)


def post_ratelimited_kelderapi_error(message):
    '''Post error message to verbose-mattermost channel. Only posts one message every 5 minutes'''
    last_posted_error_timestring = get_persistent_kv(KV_KEY_KELDERAPI_LAST_ERROR_MESSAGE, "0")
    last_posted_error_datetime = datetime.fromtimestamp(float(last_posted_error_timestring.value))
    error_count = get_persistent_kv(KV_KEY_KELDERAPI_ERROR_COUNT, "0")
    if datetime.now() - last_posted_error_datetime > timedelta(hours=1):
        last_posted_error_timestring.value = str(datetime.now().timestamp())
        last_posted_error_timestring.save()
        if int(error_count.value):
            message += f"\n and {error_count.value} error message(s) not posted to this channel"
        mattermost_doorkeeper_message(
            message,
            webhook=config.debug_webhook,
        )
        error_count.value = "0"
        error_count.save()
    else:
        error_count.value = str(int(error_count.value) + 1)
        error_count.save()


@doorkeeper_blueprint.route("/doorkeeper", methods=["POST"])
def doorkeeper():
    raw_data = request.get_data()
    hmac_header = bytearray.fromhex(request.headers.get("HMAC"))
    calculated_hash = hmac.new(
        config.up_key.encode("utf8"), raw_data, hashlib.sha256
    ).digest()
    if hmac_header != calculated_hash:
        print(f"WRONG: {hmac_header} != {calculated_hash}", file=sys.stderr)
        return abort(401)

    data_dict = {
        l.split("=")[0]: l.split("=")[1] for l in raw_data.decode("utf8").split("&")
    }
    cmd = data_dict["cmd"]
    reason = data_dict["why"]
    value = data_dict["val"]
    try:
        requests.post(
            config.kelderapi_doorkeeper_url,
            json=data_dict,
            headers={"Token": config.kelderapi_doorkeeper_key},
            timeout=3,
        )
    except requests.exceptions.RequestException as e:
        post_ratelimited_kelderapi_error(
            f"Posting `{data_dict}` to kelderapi failed\n```\n{e.__class__.__name__}: {e}\n```",
        )
    except:
        post_ratelimited_kelderapi_error(
            f"Posting `{data_dict}` to kelderapi failed\n```\n{traceback.format_exc()}\n```",
        )
    if reason == "mattermore":
        if cmd == "status":
            return ""
        msg = f'"{cmd}" command from Mattermost handled'
    elif reason == "boot":
        msg = "lockbot booted"
    elif reason == "panic":
        msg = f"@sysadmin: the door panicked with reason {cmd}"
    elif reason == "state":
        msg = f"The door is now {DOOR_STATUS[value]}"
        if not in_electronic_action_period():
            mattermost_doorkeeper_message(
                f"@bestuur: door manually went to {DOOR_STATUS[value]} state"
            )
    elif reason == "chal":
        return ""
    elif reason == "delaybutton":
        msg = "Delayed door close button was pressed"
        mark_door_electronically_used()
    else:
        msg = f"Unhandled message type: {cmd},{reason},{value}"
    mattermost_doorkeeper_message(msg, webhook=config.debug_webhook)
    return "OK"
