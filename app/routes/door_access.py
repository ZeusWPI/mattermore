from flask import Blueprint, request

from app import models
from app.app import db
from app.util import (
    get_actual_username,
    get_mattermost_id,
    mattermost_response,
    requires_admin,
    requires_token,
)


door_access_blueprint = Blueprint("door_access_blueprint", __name__)


@door_access_blueprint.route("/authorize", methods=["POST"])
@requires_token("authorize")
@requires_admin
def authorize(admin_user):
    """Slash-command to authorize a new user or modify an existing user"""
    tokens = request.values.get("text").strip().split()
    if not tokens:
        # list authorized user
        response = "\n".join(
            f'{"**" if u.admin else ""}{u.username}{" ADMIN**" if u.admin else ""}'
            for u in models.User.query.filter_by(authorized=True).order_by(
                models.User.username
            )
        )
        return mattermost_response(response, ephemeral=True)
    if len(tokens) > 2:
        return mattermost_response(
            "To authorize a user: /authorize username [admin]\nTo list authorized users: /authorize",
            ephemeral=True,
        )
    to_authorize_username = get_actual_username(tokens[0])
    to_authorize_id = get_mattermost_id(to_authorize_username)
    if to_authorize_id is None:
        return mattermost_response(
            "User '{}' does not seem to exist in Mattermost".format(
                to_authorize_username
            ),
            ephemeral=True,
        )
    as_admin = len(tokens) == 2 and tokens[1] == "admin"
    user = models.User.query.filter_by(mattermost_id=to_authorize_id).first()
    if not user:
        user = models.User(to_authorize_username)
        user.mattermost_id = to_authorize_id
    user.authorized = True
    user.admin = as_admin or user.admin
    db.session.add(user)
    db.session.commit()
    if user.admin:
        return mattermost_response("'{}' is now an admin".format(to_authorize_username))
    else:
        return mattermost_response(
            "'{}' is now a regular user".format(to_authorize_username)
        )


@door_access_blueprint.route("/revoke", methods=["POST"])
@requires_token("revoke")
@requires_admin
def revoke(admin_username):
    """Slash-command to revoke a user"""
    tokens = request.values.get("text").strip().split()
    to_revoke_username = get_actual_username(tokens[0])
    to_revoke_id = get_mattermost_id(to_revoke_username)
    if to_revoke_id is None:
        return mattermost_response(
            "Could not find '{}' in Mattermost".format(to_revoke_username)
        )
    user = models.User.query.filter_by(mattermost_id=to_revoke_id).first()
    if user is None:
        return mattermost_response(
            "Could not find '{}' in our database".format(to_revoke_username)
        )
    if user.admin:
        return mattermost_response("Can't revoke admin user")
    user.authorized = False
    db.session.add(user)
    db.session.commit()
    return mattermost_response("'{}' revoked".format(to_revoke_username))
