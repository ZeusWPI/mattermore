import json
from functools import wraps
from flask import Flask, request, Response, abort, render_template, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime
from mattermostdriver import Driver
import requests
import config
import random
import hashlib
import hmac
import re
import sys
import time
import traceback


app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = config.DATABASE_URL
# Supress Flask warning
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

response_setting = "in_channel"

# Login driver: used to send messages to Mattermost
mm_driver = Driver({
        'port': 443,
        'url': config.server_url,
        'token': config.mm_driver_token
    })
mm_driver.login()

DOOR_STATUS = {
    '0': 'locked',
    '1': 'open',
    '2': 'inbetween'
}

from app import models
from app import cron


def get_mattermost_id(username):
    '''Given a mattermost username, return the user id. Don't call this with stale data'''
    try:
        response = mm_driver.users.get_user_by_username(username)
        return response['id']
    except:
        return None


def query_and_update_username():
    '''Updates mattermost data if need be. Only use in requests.'''
    mattermost_user_id = request.values.get('user_id')
    username = request.values.get('user_name')
    user = models.User.query.filter_by(mattermost_id=mattermost_user_id).first()
    if not user:
        return None
    if user.username != username:
        user.username = username
        db.session.add(user)
        db.session.commit()
    return user


def requires_regular(f):
    '''Decorator to require a regular user'''
    @wraps(f)
    def decorated(*args, **kwargs):
        user = query_and_update_username()
        if not user or not user.authorized:
            return abort(401)
        return f(user, *args, **kwargs)
    return decorated


def requires_admin(f):
    '''Decorator to require an admin user'''
    @wraps(f)
    def decorated(*args, **kwargs):
        user = query_and_update_username()
        if not user or not user.authorized or not user.admin:
            return abort(401)
        return f(user, *args, **kwargs)
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


def mattermost_doorkeeper_message(message, webhook=config.doorkeeper_webhook):
    requests.post(webhook, json={"text": message})

# Removes @ from username if @ was prepended
def get_actual_username(username):
    return username.lstrip('@')


@app.route('/authorize', methods=['POST'])
@requires_token('authorize')
@requires_admin
def authorize(admin_user):
    '''Slash-command to authorize a new user or modify an existing user'''
    tokens = request.values.get('text').strip().split()
    if not tokens:
        # list authorized user
        response = '\n'.join(f'{"**" if u.admin else ""}{u.username}{" ADMIN**" if u.admin else ""}' for u in models.User.query.filter_by(authorized=True).order_by(models.User.username))
        return mattermost_response(response, ephemeral=True)
    if len(tokens) > 2:
        return mattermost_response("To authorize a user: /authorize username [admin]\nTo list authorized users: /authorize", ephemeral=True)
    to_authorize_username = get_actual_username(tokens[0])
    to_authorize_id = get_mattermost_id(to_authorize_username)
    if to_authorize_id is None:
        return mattermost_response("User '{}' does not seem to exist in Mattermost".format(to_authorize_username), ephemeral=True)
    as_admin = len(tokens) == 2 and tokens[1] == 'admin'
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
        return mattermost_response("'{}' is now a regular user".format(to_authorize_username))


@app.route('/revoke', methods=['POST'])
@requires_token('revoke')
@requires_admin
def revoke(admin_username):
    '''Slash-command to revoke a user'''
    tokens = request.values.get('text').strip().split()
    to_revoke_username = get_actual_username(tokens[0])
    to_revoke_id = get_mattermost_id(to_revoke_username)
    if to_revoke_id is None:
        return mattermost_response("Could not find '{}' in Mattermost".format(to_revoke_username))
    user = models.User.query.filter_by(mattermost_id=to_revoke_id).first()
    if user is None:
        return mattermost_response("Could not find '{}' in our database".format(to_revoke_username))
    if user.admin:
        return mattermost_response("Can't revoke admin user")
    user.authorized = False
    db.session.add(user)
    db.session.commit()
    return mattermost_response("'{}' revoked".format(to_revoke_username))


def lockbot_request(command):
    # TODO: fix this properly with a mutex
    # TODO: cache status requests
    timestamp = int(time.time()*1000)
    payload = f'{timestamp};{command}'
    calculated_hmac = hmac.new(config.down_key.encode('utf8'), payload.encode('utf8'), hashlib.sha256).hexdigest().upper()
    r = requests.post(config.lockbot_url, payload, headers={'HMAC': calculated_hmac})
    return DOOR_STATUS[r.text]

@app.route('/door', methods=['POST'])
@requires_token('door')
@requires_regular
def door(user):
    tokens = request.values.get('text').strip().split()
    command = tokens[0].lower()
    if command == 'getkey':
        user.generate_key()
        db.session.add(user)
        db.session.commit()
        return mattermost_response(f'Your key is {user.doorkey}, the URLs you can POST to are https://mattermore.zeus.gent/api/door/{user.doorkey}/open and https://mattermore.zeus.gent/api/door/{user.doorkey}/lock', ephemeral=True)
    if command == 'close':
        command = 'lock'
    if command not in ('open', 'lock', 'status'):
        return mattermost_response('Only [open|lock|status|getkey] subcommands supported', ephemeral=True)
    translated_state_before_command = lockbot_request(command)
    if command != 'status':
        mattermost_doorkeeper_message(f'door was {translated_state_before_command}, {user.username} tried to {command} door')
    return mattermost_response(translated_state_before_command, ephemeral=True)

@app.route('/api/door/<doorkey>/<command>', methods=['POST'])
def doorapi(doorkey, command):
    if not doorkey:
        return abort(401)
    user = models.User.query.filter_by(doorkey=doorkey, authorized=True).first()
    if user is None:
        return abort(401)
    if command not in ('open', 'lock', 'status'):
        return abort(400, "Command not in (open,lock,status)")
    translated_state_before_command = lockbot_request(command)
    if command != 'status':
        mattermost_doorkeeper_message(f'door was {translated_state_before_command}, {user.username} tried to {command} door via the API')
    return jsonify({'status': 'ok','before': translated_state_before_command})

@app.route('/spaceapi.json')
def spaceapi():
    # door_status = lockbot_request('status')
    # status = door_status == 'open'
    status = None
    response = jsonify({
        "api": "0.13",
        "space": "Zeus WPI",
        "logo": "https://zinc.zeus.gent",
        "url": "https://zeus.ugent.be",
        "location": {
                "address": "Zeuskelder, gebouw S9, Krijgslaan 281, Ghent, Belgium",
                "lon": 3.7102741,
                "lat": 51.0231119,
        },
        "contact": {
            "email": "bestuur@zeus.ugent.be",
            "twitter": "@ZeusWPI"
        },
        "issue_report_channels": ["email"],
        "state": {
            "icon": {
                "open": "https://zinc.zeus.gent/zeus",
                "closed": "https://zinc.zeus.gent/black"
            },
            "open": status
        },
        "projects": [
            "https://github.com/zeuswpi",
            "https://git.zeus.gent"
        ]
    })
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

@app.route('/doorkeeper', methods=['POST'])
def doorkeeper():
    raw_data = request.get_data()
    hmac_header = bytearray.fromhex(request.headers.get('HMAC'))
    calculated_hash = hmac.new(config.up_key.encode('utf8'), raw_data, hashlib.sha256).digest()
    if hmac_header != calculated_hash:
        print(f"WRONG: {hmac_header} != {calculated_hash}", file=sys.stderr)
        return abort(401)

    data_dict = {l.split('=')[0]: l.split('=')[1] for l in raw_data.decode('utf8').split('&')}
    cmd = data_dict['cmd']
    reason = data_dict['why']
    value = data_dict['val']
    try:
        requests.post(config.kelderapi_doorkeeper_url, json=data_dict, headers={'Token': config.kelderapi_doorkeeper_key}, timeout=3)
    except requests.exceptions.RequestException as e:
         mattermost_doorkeeper_message(f"Posting {data_dict} to kelderapi failed\n```\n{e.__class__.__name__}: {e}\n```", webhook=config.debug_webhook)
    except:
        mattermost_doorkeeper_message(f"Posting {data_dict} to kelderapi failed\n```\n{traceback.format_exc()}\n```", webhook=config.debug_webhook)
    if reason == 'mattermore':
        if cmd == 'status':
            return ''
        msg = f'"{cmd}" command from Mattermost handled'
    elif reason == 'boot':
        msg = 'lockbot booted'
    elif reason == 'panic':
        msg = f'@sysadmin: the door panicked with reason {cmd}'
    elif reason == 'state':
        msg = f'The door is now {DOOR_STATUS[value]}'
    elif reason == 'chal':
        return ''
    elif reason == 'delaybutton':
        msg = 'Delayed door close button was pressed'
    else:
        msg = f'Unhandled message type: {cmd},{reason},{value}'
    mattermost_doorkeeper_message(msg, webhook=config.debug_webhook)
    return "OK"

@app.route('/cammiechat', methods=['POST'])
@requires_token('cammiechat')
@requires_regular
def cammiechat(user):
    headers = {
        "X-Username": user.username
    }
    requests.post("https://kelder.zeus.ugent.be/messages/", data=request.values.get('text').strip(), headers=headers, timeout=5)
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
    return send_file('static/robots.txt')


@app.route('/fonts/<filename>', methods=['GET'])
def get_font(filename):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]*\.(?:otf|svg|woff2?)', filename):
        return abort(404)

    return send_file('static/fonts/' + filename)


@app.route('/quotes.css', methods=['GET'])
def get_quote_css():
    return send_file('static/quotes.css')


@app.route('/quotes.html', methods=['GET'])
def list_quotes():
    return render_template('quotes.html', quotes=reversed(models.Quote.query.all()))


@app.route('/quotes.json', methods=['GET'])
def json_quotes():
    all_quotes = models.Quote.query.all()
    response = jsonify(list({
        'quoter': q.quoter,
        'quotee': q.quotee,
        'channel': q.channel,
        'quote': q.quote,
        'created_at': q.created_at.isoformat()
    } for q in all_quotes))
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

RESTO_TEMPLATE = """
# Restomenu

## Woater me e smaksje
{soup_table}

## Vleesch
{meat_table}

## Visch
{fish_table}

## Vegetoarisch
{vegi_table}
{uncategorized}
## Groensels
{vegetable_table}

"""

UNCATEGORIZED_TEMPLATE = """
## Nog etwad anders...
{}
"""

RESTO_TABLES = {
    "soup_table": {"soup"},
    "meat_table": {"meat"},
    "fish_table": {"fish"},
    "vegi_table": {"vegetarian", "vegan"},
}

@app.route('/resto', methods=['GET'])
def resto_menu():
    today = datetime.today()
    url = f"https://hydra.ugent.be/api/2.0/resto/menu/nl/{today.year}/{today.month}/{today.day}.json"
    resto = requests.get(url, timeout=5).json()

    if not resto["open"]:
        return 'De resto is vandaag gesloten.'
    else:
        def table_for(kinds):
            items = [meal for meal in resto["meals"] if meal["kind"] in kinds]
            return format_items(items)

        def format_items(items):
            if not items:
                return "None :("
            maxwidth = max(len(item["name"]) for item in items)
            return "\n".join("{name: <{width}}{price}".format(
                    name=item["name"],
                    width=maxwidth + 2,
                    price=item["price"])
                for item in items
                )

        recognized_kinds = set.union(*RESTO_TABLES.values())
        uncategorized_meals = [
                meal for meal in resto["meals"]
                if meal["kind"] not in recognized_kinds
                ]

        uncategorized = "" if not uncategorized_meals else \
            UNCATEGORIZED_TEMPLATE.format(
                format_items([
                    # Small hack: change "name" into "name (kind)"
                    {**meal, "name": "{} ({})".format(meal["name"], meal["kind"])}
                    for meal in uncategorized_meals
                ])
            )

        return RESTO_TEMPLATE.format(
                **{k: table_for(v) for k,v in RESTO_TABLES.items()},
                uncategorized=uncategorized,
                vegetable_table="\n".join(resto["vegetables"])
                )

@app.route('/resto.json', methods=['GET'])
def resto_menu_json():
    return mattermost_response(resto_menu(), ephemeral=True)
