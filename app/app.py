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

from app import models
from app import cron

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


# Removes @ from username if @ was prepended
def get_actual_username(username):
    return username.lstrip('@')


@app.route('/authorize', methods=['POST'])
@requires_token('authorize')
@requires_admin
def authorize(admin_username):
    '''Slash-command to authorize a new user or modify an existing user'''
    tokens = request.values.get('text').strip().split()
    to_authorize = get_actual_username(tokens[0])
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
    to_revoke = get_actual_username(tokens[0])
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
    r = requests.post(config.slotmachien_url, json={
        'username': username, 'token': config.slotmachien_token, 'text': command}, timeout=5)
    return r.text


@app.route('/door', methods=['POST'])
@requires_token('door')
@requires_regular
def door(username):
    tokens = request.values.get('text').strip().split()
    command = tokens[0].lower()
    return mattermost_response(slotmachien_request(username, command), ephemeral=True)

@app.route('/spaceapi.json')
def spaceapi():
    cammiestatus = requests.get('https://kelder.zeus.ugent.be/webcam/cgi/ptdc.cgi', timeout=5)
    # Avoid XML parsing
    status = '<lightADC>0</lightADC>' not in cammiestatus.text
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
@requires_token('doorkeeper')
def doorkeeper():
    username = request.values.get('user').strip()
    command = request.values.get('command').strip()
    if command == 'open':
        msg = '%s has opened the door' % (username)
    elif command == 'close':
        msg = '%s has closed the door' % (username)
    elif command == 'delay':
        msg = 'Door is closing in 10 seconds by %s' % (username)
    else:
        msg = 'I\'m sorry Dave, I\'m afraid I can\'t do that'
    resp = mm_driver.posts.create_post(options={
                'channel_id': config.doorkeeper_channel_id,
                'message': msg
            })
    if resp is not None:
        return Response(status=200)
    else:
        return Response(status=500)

@app.route('/cammiechat', methods=['POST'])
@requires_token('cammiechat')
@requires_regular
def cammiechat(username):
    headers = {
        "X-Username": username
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
    url = "https://zeus.ugent.be/hydra/api/2.0/resto/menu/nl/{}/{}/{}.json"\
            .format(today.year, today.month, today.day)
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
