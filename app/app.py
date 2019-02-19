import json
from functools import wraps
from flask import Flask, request, Response, abort, render_template, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime
import requests
import config
import random
import re
import pdb
from mattermostdriver import Driver

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = config.DATABASE_URL
# Supress Flask warning
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

response_setting = "in_channel"

from app import models

driver = Driver({
    'url': config.server_url,
    'token': config.personal_auth_token
})

driver.login()

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

def is_bestuur(username):
    return username in config.bestuur

@app.route('/new_message', methods=['POST'])
def new_message():
    if not is_bestuur(request.values.get("user_name")):
        delete_message(request.values.get("post_id"))
    return ""

def delete_message(message_id):
    driver.posts.delete_post(message_id)

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


@app.route('/addquote', methods=['POST'])
@requires_token('quote')
def add_quote():
    user = request.values['user_name']
    channel = request.values['channel_name']
    quote_text = request.values['text']
    quote = models.Quote(user, quote_text, channel)
    db.session.add(quote)
    db.session.commit()
    return mattermost_response("{} added the quote \"{}\"".format(user, quote_text))


@app.route('/quote', methods=['POST'])
def random_quote():
    text_contains = request.values['text']
    matches = models.Quote.query.filter(models.Quote.quote.contains(text_contains)).all()
    if matches:
        selected_quote = random.choice(matches)
        response = selected_quote.quote
        return mattermost_response(response)
    return mattermost_response('No quotes found matching "{}"'.format(text_contains), ephemeral=True)


@app.route('/robots.txt', methods=['GET'])
def get_robots():
    return send_file('templates/robots.txt')


@app.route('/quotes.html', methods=['GET'])
def list_quotes():
    return render_template('quotes.html', quotes=reversed(models.Quote.query.all()))


@app.route('/quotes.json', methods=['GET'])
def json_quotes():
    all_quotes = models.Quote.query.all()
    return jsonify(list({
        'quoter': q.quoter,
        'quotee': q.quotee,
        'channel': q.channel,
        'quote': q.quote,
        'created_at': q.created_at.isoformat()
    } for q in all_quotes))

RESTO_TEMPLATE = """
# Resto menu

## Soepjes
{soup_table}

## Vleesjes
{meat_table}

## Visjes
{fish_table}

## Niet-vleesjes
{vegi_table}

## Groentjes
{vegetable_table}

"""

@app.route('/resto', methods=['GET'])
def resto_menu():
    today = datetime.today()
    url = "https://zeus.ugent.be/hydra/api/2.0/resto/menu/nl/{}/{}/{}.json"\
            .format(today.year, today.month, today.day)
    resto = requests.get(url).json()

    if not resto["open"]:
        return 'De resto is vandaag gesloten.'
    else:
        def table_for(kind):
            items = [meal for meal in resto["meals"] if meal["kind"] == kind]
            maxwidth = max(map(lambda item: len(item["name"]), items))
            return "\n".join("{name: <{width}}{price}".format(
                    name=item["name"],
                    width=maxwidth + 2,
                    price=item["price"])
                for item in items
                )

        return RESTO_TEMPLATE.format(
                soup_table=table_for("soup"),
                meat_table=table_for("meat"),
                fish_table=table_for("fish"),
                vegi_table=table_for("vegetarian"),
                vegetable_table="\n".join(resto["vegetables"])
                )

@app.route('/resto.json', methods=['GET'])
def resto_menu_json():
    return mattermost_response(resto_menu(), ephemeral=True)


