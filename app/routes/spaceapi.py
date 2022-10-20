from flask import Blueprint, jsonify

from app.util import lockbot_request


spaceapi_blueprint = Blueprint("spaceapi", __name__)


@spaceapi_blueprint.route("/spaceapi.json")
def spaceapi():
    door_status = lockbot_request("status")
    # Avoid XML parsing
    status = door_status == "open"
    response = jsonify(
        {
            "api": "0.13",
            "space": "Zeus WPI",
            "logo": "https://zinc.zeus.gent",
            "url": "https://zeus.ugent.be",
            "location": {
                "address": "Zeuskelder, gebouw S9, Krijgslaan 281, Ghent, Belgium",
                "lon": 3.7102741,
                "lat": 51.0231119,
            },
            "contact": {"email": "bestuur@zeus.ugent.be", "twitter": "@ZeusWPI"},
            "issue_report_channels": ["email"],
            "state": {
                "icon": {
                    "open": "https://zinc.zeus.gent/zeus",
                    "closed": "https://zinc.zeus.gent/black",
                },
                "open": status,
            },
            "projects": ["https://github.com/zeuswpi", "https://git.zeus.gent"],
        }
    )
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response
