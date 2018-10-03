import json
from functools import wraps
from flask import Flask, request, Response, abort
from flask_sqlalchemy import SQLAlchemy
import requests
import config

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = config.DATABASE_URL
# Supress Flask warning
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

response_setting = "in_channel"

from app import models

@app.route('/', methods=['GET'])
def hello_world():
    message = "It's aliiiiiiiiiiiiiiiiiiiiiive!\n"
    message += f"There are {models.User.query.count()} users in the database."
    return message

def check_regular(username):
    '''Check if a user has the permissions of a regular user.'''
    return models.User.query.filter_by(username=username, authorized=True).first() is not None


def check_admin(username):
    '''Check if a user is an admin'''
    return models.User.query.filter_by(username=username, authorized=True, admin=True).first() is not None


def requires_regular(f):
    '''Decorator to require a regular user'''
    @wraps(f)
    def decorated(*args, **kwargs):
        username = request.values.get('user_name')
        if not username or not check_regular(username):
            return abort(401)
        return f(username, *args, **kwargs)
    return decorated


def requires_admin(f):
    '''Decorator to require an admin user'''
    @wraps(f)
    def decorated(*args, **kwargs):
        username = request.values.get('user_name')
        if not username or not check_admin(username):
            return abort(401)
        return f(username, *args, **kwargs)
    return decorated


def requires_token(token_name):
    '''Decorator to require a correct Mattermost token'''
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            expected_token = config.tokens[token_name]
            token = request.values.get('token')
            print(token, expected_token)
            if expected_token != token:
                return abort(401)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def mattermost_response(message, ephemeral=False):
    response_dict = {"response_type": "ephemeral" if ephemeral else "in_channel",
                     "text": message}
    return Response(json.dumps(response_dict), mimetype="application/json")


@app.route('/authorize', methods=['POST'])
@requires_token('authorize')
@requires_admin
def authorize(admin_username):
    '''Slash-command to authorize a new user or modify an existing user'''
    tokens = request.values.get('text').strip().split()
    to_authorize = tokens[0]
    as_admin = len(tokens) == 2 and tokens[1] == 'admin'
    user = models.User.query.filter_by(username=to_authorize).first()
    if not user:
        user = models.User(to_authorize)
    user.authorized = True
    user.admin = as_admin or user.admin
    db.session.add(user)
    db.session.commit()
    if user.admin:
        return mattermost_response("'{}' is now an admin".format(to_authorize))
    else:
        return mattermost_response("'{}' is now a regular user".format(to_authorize))


@app.route('/revoke', methods=['POST'])
@requires_token('revoke')
@requires_admin
def revoke(admin_username):
    '''Slash-command to revoke a user'''
    tokens = request.values.get('text').strip().split()
    to_revoke = tokens[0]
    user = models.User.query.filter_by(username=to_revoke).first()
    if not user:
        return mattermost_response("Could not find '{}'".format(to_revoke))
    if user.admin:
        return mattermost_response("Can't revoke admin user")
    user.authorized = False
    db.session.add(user)
    db.session.commit()
    return mattermost_response("'{}' revoked".format(to_revoke))


def slotmachien_request(username, command):
    r = requests.post(config.slotmachien_url, data={
        'username': username, 'token': config.slotmachien_token, 'text': command})
    return r.text


@app.route('/door', methods=['POST'])
@requires_token('door')
@requires_regular
def door(username):
    tokens = request.values.get('text').strip().split()
    command = tokens[0].lower()
    return mattermost_response(slotmachien_request(username, command), ephemeral=True)

@app.route('/cammiechat', methods=['POST'])
@requires_token('cammiechat')
@requires_regular
def cammiechat(username):
    headers = {
            "X-Username": username
    }
    requests.post("https://kelder.zeus.ugent.be/messages/", data=request.values.get('text').strip(), headers=headers)
    return mattermost_response("Message sent", ephemeral=True)
