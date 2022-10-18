from flask import Blueprint, request
import requests

from app.app import mattermost_response, requires_regular, requires_token


cammie_blueprint = Blueprint("cammie", __name__)


@cammie_blueprint.route("/cammiechat", methods=["POST"])
@requires_token("cammiechat")
@requires_regular
def cammiechat(user):
    headers = {"X-Username": user.username}
    requests.post(
        "https://kelder.zeus.ugent.be/messages/",
        data=request.values.get("text").strip(),
        headers=headers,
        timeout=5,
    )
    return mattermost_response("Message sent", ephemeral=True)
