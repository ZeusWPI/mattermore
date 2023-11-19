from flask import Blueprint, jsonify

from app.util import lockbot_request


spaceapi_blueprint = Blueprint("spaceapi", __name__)


@spaceapi_blueprint.route("/spaceapi.json")
def spaceapi():
    data = {
        "api": "0.13",
        "space": "Zeus WPI",
        "logo": "https://zinc.zeus.gent",
        "url": "https://zeus.ugent.be",
        "location": {
            "address": "Zeuskelder, gebouw S9, Krijgslaan 281, Ghent, Belgium",
            "lon": 3.7102741,
            "lat": 51.0231119,
        },
        "contact": {"email": "bestuur@zeus.ugent.be"},
        "issue_report_channels": ["email"],
        "state": {
            "icon": {
                "open": "https://zinc.zeus.gent/zeus",
                "closed": "https://zinc.zeus.gent/black",
            },
        },
        "projects": ["https://github.com/zeuswpi", "https://git.zeus.gent"],
    }
    door_status = lockbot_request("status", use_cache=True)
    if door_status == "open":
        data["state"]["open"] = True
    elif door_status == "locked":
        data["state"]["open"] = False
    # Else, don't put the 'open' property in the response, to indicate temporary unavailability
    #  per https://spaceapi.io/docs/#schema-key-state
    response = jsonify(data)
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response
