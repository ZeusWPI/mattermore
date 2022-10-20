from flask import Blueprint, abort, request
import hashlib
import hmac
import requests
import sys
import traceback

from app.app import DOOR_STATUS
from app.util import mattermost_doorkeeper_message

import config

doorkeeper_blueprint = Blueprint("doorkeeper", __name__)


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
        mattermost_doorkeeper_message(
            f"Posting `{data_dict}` to kelderapi failed\n```\n{e.__class__.__name__}: {e}\n```",
            webhook=config.debug_webhook,
        )
    except:
        mattermost_doorkeeper_message(
            f"Posting `{data_dict}` to kelderapi failed\n```\n{traceback.format_exc()}\n```",
            webhook=config.debug_webhook,
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
    elif reason == "chal":
        return ""
    elif reason == "delaybutton":
        msg = "Delayed door close button was pressed"
    else:
        msg = f"Unhandled message type: {cmd},{reason},{value}"
    mattermost_doorkeeper_message(msg, webhook=config.debug_webhook)
    return "OK"
