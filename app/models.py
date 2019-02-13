from .app import db
from datetime import datetime
import re


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    authorized = db.Column(db.Boolean, default=True)
    admin = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return '<User %r>' % self.username

    def __init__(self, username, admin=False):
        super()
        self.username = username
        self.admin = admin

class Quote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quoter = db.Column(db.String(255), unique=False, nullable=False)
    quotee = db.Column(db.String(255), unique=False, nullable=True)
    channel = db.Column(db.String(255), unique=False, nullable=False)
    quote = db.Column(db.String(1023), unique=True,  nullable=False)
    created_at = db.Column(
            db.DateTime, nullable=False,
            default=datetime.utcnow
            )

    QUOTEE_REGEX = re.compile('\W*(\w+).*')

    def __repr__(self):
        return f"<Quote {self.quoter} \"{self.quote}\">"

    def __init__(self, quoter, quote, channel):
        super()
        self.quoter = quoter
        self.quote = quote
        self.channel = channel
        self.created_at = datetime.utcnow()
        # Experimentally try to find quoted user
        quotee_match = Quote.QUOTEE_REGEX.search(quote)
        self.quotee = quotee_match.group(1) if quotee_match is not None else None

