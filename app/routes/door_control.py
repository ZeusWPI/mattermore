from flask import Blueprint, abort, jsonify, request

from app import models
from app.app import db
from app.util import (
    lockbot_request,
    mattermost_doorkeeper_message,
    mattermost_response,
    requires_regular,
    requires_token,
)


door_control_blueprint = Blueprint("door_control", __name__)


@door_control_blueprint.route("/door", methods=["POST"])
@requires_token("door")
@requires_regular
def door(user):
    tokens = request.values.get("text").strip().split()
    command = tokens[0].lower()
    if command == "getkey":
        user.generate_key()
        db.session.add(user)
        db.session.commit()
        return mattermost_response(
            f"WARNING: door should only be operated when you are physically at the door. Your key is {user.doorkey}, the URLs you can POST to are https://mattermore.zeus.gent/api/door/{user.doorkey}/open and https://mattermore.zeus.gent/api/door/{user.doorkey}/lock",
            ephemeral=True,
        )
    if command == "close":
        command = "lock"
    if command not in ("open", "lock", "status"):
        return mattermost_response(
            "Only [open|lock|status|getkey] subcommands supported", ephemeral=True
        )
    translated_state_before_command = lockbot_request(command)
    if command != "status":
        mattermost_doorkeeper_message(
            f"door was {translated_state_before_command}, {user.username} tried to {command} door"
        )
    return mattermost_response(translated_state_before_command, ephemeral=True)


@door_control_blueprint.route("/api/door/<doorkey>/<command>", methods=["POST"])
def doorapi(doorkey, command):
    if not doorkey:
        return abort(401)
    user = models.User.query.filter_by(doorkey=doorkey, authorized=True).first()
    if user is None:
        return abort(401)
    if command not in ("open", "lock", "status"):
        return abort(400, "Command not in (open,lock,status)")
    translated_state_before_command = lockbot_request(command)
    if command != "status":
        mattermost_doorkeeper_message(
            f"door was {translated_state_before_command}, {user.username} tried to {command} door via the API"
        )
    return jsonify({"status": "ok", "before": translated_state_before_command})
