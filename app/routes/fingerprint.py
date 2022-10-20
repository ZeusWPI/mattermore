from collections import defaultdict
from datetime import datetime
from typing import Any
from flask import Blueprint, Response, request
import hashlib
import hmac
import requests
import time

from app import models
from app.util import (
    lockbot_request,
    mattermost_doorkeeper_message,
    mattermost_response,
    requires_regular,
    requires_token,
)

import config


fingerprint_blueprint = Blueprint("fingerprint", __name__)


def fingerprint_request(command: str, data: Any = None) -> "requests.Response":
    """
    Send a command to the fingerprint sensor, returns the sensors response
    """

    timestamp = int(time.time() * 1000)
    payload = f"{timestamp};{command};{data};" if data else f"{timestamp};{command};"
    calculated_hmac = (
        hmac.new(config.down_key.encode("utf8"), payload.encode("utf8"), hashlib.sha256)
        .hexdigest()
        .upper()
    )
    return requests.post(
        config.fingerprint_url, payload, headers={"HMAC": calculated_hmac}
    )


def get_free_fp_ids() -> set[int]:
    """Get a set of all available fingerprint IDs"""

    res = fingerprint_request("list")

    id_list = list(res.text)
    used_ids = set()
    for i, val in enumerate(id_list):
        if val == "1":
            used_ids.add(i)

    all_ids = set(range(1, 201))
    return all_ids.difference(used_ids)


def pretty_user_fingerprints(d: dict[str, list[str]]) -> str:
    """Pretty print a dict of users and their fingerprints"""

    repr = ""

    for k, v in d.items():
        repr += f"{k}\n"
        for f in v:
            repr += f"\t{f}\n"

    return repr


def send_fingerprint_delete(ids: list[int]):
    """Mass delete a list of fingerprints"""

    for id_ in ids:
        fingerprint_request("delete", id_)


@fingerprint_blueprint.route("/fingerprint", methods=["POST"])
@requires_token("fingerprint")
@requires_regular
def fingerprint(user):
    tokens = request.values.get("text").strip().split()
    try:
        command = tokens[0].lower()
    except IndexError:
        return mattermost_response(
            "Only [enroll|delete|list] subcommands supported", ephemeral=True
        )

    user_id = (
        models.User.query.filter(models.User.username == user.username)
        .from_self(models.User.id)
        .scalar()
    )

    if command == "enroll":
        try:
            fp_note = tokens[1].lower()
        except IndexError:
            return mattermost_response(
                "Missing or invalid fingerprint note, syntax: /fingerprint enroll \{note\}\n\{note\} must not contain spaces",
                ephemeral=True,
            )

        # Ensure that no pending fingerprints remain (this only rarely do something)
        deleted_ids = models.Fingerprint.clear_inactive()
        send_fingerprint_delete(deleted_ids)

        ids = get_free_fp_ids()
        if len(ids) == 0:
            return mattermost_response(
                "Cannot enroll fingerprint, no free slots left", ephemeral=True
            )

        fp_id = min(ids)
        fingerprint_request("enroll", fp_id)

        models.Fingerprint.create(fp_id, user_id, fp_note, datetime.now())

        print(
            f"created inactive fingerprint {fp_id} for user {user.username} with note {fp_note}"
        )
        return mattermost_response(
            f"Started enrolling fingerprint #{fp_id} for user '{user.username}'",
            ephemeral=True,
        )

    if command == "delete":
        try:
            fp_note = tokens[1].lower()
        except IndexError:
            return mattermost_response(
                "Missing or invalid fingerprint note, syntax: /fingerprint delete \{note\}\n\{note\} must not contain spaces",
                ephemeral=True,
            )

        fingerprint = None
        username = user.username
        if user.admin:
            if len(tokens) == 2:
                fingerprint = models.Fingerprint.find(user_id, fp_note)
            elif len(tokens) == 3:
                username = tokens[2]

                other_user_id = (
                    models.User.query.filter(models.User.username == username)
                    .from_self(models.User.id)
                    .scalar()
                )
                fingerprint = models.Fingerprint.find(other_user_id, fp_note)
        else:
            fingerprint = models.Fingerprint.find(user_id, fp_note)

        if fingerprint is None:
            return mattermost_response(
                f"No fingerprint with note '{fp_note}' found for user '{username}'",
                ephemeral=True,
            )

        fingerprint_request("delete", fingerprint.id)

        print(f"sent command delete fingerprint {fp_note} for {username}")
        return mattermost_response(
            f"Deleted fingerprint '{fp_note}' for user '{username}'",
            ephemeral=True,
        )

    if command == "list":
        data = models.User.get_user_fingerprints()
        user_fingerprints = defaultdict(list)
        for datum in data:
            user_fingerprints[datum[0].username].append(datum[1].note)

        if not user.admin:
            if len(user_fingerprints[user.username]) != 0:
                msg = user_fingerprints[user.username]
            else:
                msg = "No fingerprints found"

            return mattermost_response(msg, ephemeral=True)

        if len(user_fingerprints) == 0:
            return mattermost_response("No fingerprints found", ephemeral=True)

        return mattermost_response(
            pretty_user_fingerprints(user_fingerprints), ephemeral=True
        )

    if command not in ("enroll", "delete", "list"):
        return mattermost_response(
            "Only [enroll|delete|list] subcommands supported", ephemeral=True
        )

    return mattermost_response("")


@fingerprint_blueprint.route("/fingerprint_cb", methods=["POST"])
def fingerprint_cb():
    msg, val = request.data.decode("utf-8").split("\n")

    if msg == "enrolled":
        fingerprint = models.Fingerprint.find_by_id(int(val))
        fingerprint.active = True
        fingerprint.save()
        print(f"[ACK] activated fingerprint {fingerprint.id} for {fingerprint.user_id}")
        mattermost_doorkeeper_message(
            f"Activated fingerprint {fingerprint.note} for user {fingerprint.user.username}",
            webhook=config.debug_webhook,
        )
    elif msg == "detected":
        fingerprint = models.Fingerprint.find_active_by_id(int(val))
        print(f"detected fingerprint {fingerprint.id}")
        user = fingerprint.user

        translated_state_before_command = lockbot_request("open")
        mattermost_doorkeeper_message(
            f"Detected fingerprint #{fingerprint.id} (user '{user.username}')",
            webhook=config.debug_webhook,
        )
        mattermost_doorkeeper_message(
            f"door was {translated_state_before_command}, {user.username} tried to open the door with the fingerprint sensor"
        )
    elif msg == "deleted":
        fingerprint = models.Fingerprint.find_by_id(int(val))
        if fingerprint is None:
            return Response("", status=200)

        note = fingerprint.note
        user = fingerprint.user
        user_id = fingerprint.user_id

        fingerprint.delete_()
        print(f"[ACK] deleted fingerprint '{note}' for '{user_id}'")
        mattermost_doorkeeper_message(
            f"Deleted fingerprint '{fingerprint.note}' for user '{user.username}'",
            webhook=config.debug_webhook,
        )

    elif msg == "missing_hmac":
        mattermost_doorkeeper_message(
            "@sysadmin Fingerprint sensor received message without HMAC signature",
            webhook=config.debug_webhook,
        )
    elif msg == "too_long":
        mattermost_doorkeeper_message(
            "@sysadmin Fingerprint sensor received message longer than 128 bytes",
            webhook=config.debug_webhook,
        )
    elif msg == "invalid_hmac":
        mattermost_doorkeeper_message(
            "@sysadmin Fingerprint sensor received message with invalid HMAC signature",
            webhook=config.debug_webhook,
        )
    elif msg == "replay":
        mattermost_doorkeeper_message(
            "@sysadmin Fingerprint sensor received message with incorrect timestamp (possible replay attack)",
            webhook=config.debug_webhook,
        )
    else:
        mattermost_doorkeeper_message(
            "@sysadmin Received invalid fingerprint callback message",
            webhook=config.debug_webhook,
        )

    return Response("", status=200)
