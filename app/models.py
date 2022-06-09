from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from .app import db
from datetime import datetime
import re
import secrets


MONTHS = [
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
]


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    authorized = db.Column(db.Boolean, default=True)
    admin = db.Column(db.Boolean, default=False)
    mattermost_id = db.Column(db.String(255))
    doorkey = db.Column(db.String(32))

    fingerprints = relationship(
        "Fingerprint", back_populates="user", cascade="all, delete, delete-orphan"
    )

    def __repr__(self):
        return "<User %r>" % self.username

    def __init__(self, username, admin=False):
        super()
        self.username = username
        self.admin = admin

    def generate_key(self):
        self.doorkey = secrets.token_urlsafe(16)


class Quote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quoter = db.Column(db.String(255), unique=False, nullable=False)
    quotee = db.Column(db.String(255), unique=False, nullable=True)
    channel = db.Column(db.String(255), unique=False, nullable=False)
    quote = db.Column(db.String(16383), unique=False, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    QUOTEE_REGEX = re.compile("\W*([a-zA-Z\-_0-9]+).*")

    def __repr__(self):
        return '<Quote {} "{}">'.format(self.quoter, self.quote)

    def __init__(self, quoter, quote, channel, created_at=None):
        super()
        self.quoter = quoter
        self.quote = quote
        self.channel = channel
        if created_at is None:
            self.created_at = datetime.utcnow()
        else:
            self.created_at = created_at
        # Experimentally try to find quoted user
        quotee_match = Quote.QUOTEE_REGEX.search(quote)
        self.quotee = quotee_match.group(1) if quotee_match is not None else None

    def slur(self):
        return self.created_at.strftime("%Y-%m-%d_%H:%M:%S")

    def created_at_machine(self):
        return self.created_at.strftime("%Y-%m-%dT%H:%M:%S%z")

    def created_at_human(self):
        c = self.created_at
        return "{} {} {:04}, {}:{:02}".format(
            c.day, MONTHS[c.month - 1], c.year, c.hour, c.minute
        )


class KeyValue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    keyname = db.Column(db.String(255), unique=True, nullable=False)
    value = db.Column(db.String(16383), unique=False, nullable=True)

    def __init__(self, keyname, value):
        super()
        self.keyname = keyname
        self.value = value

    def __repr__(self):
        return '<KeyValue {} = "{}">'.format(self.keyname, self.value)


class Fingerprint(db.Model):
    id = db.Column(db.Integer, nullable=False, unique=True, primary_key=True)
    user_id = db.Column(db.Integer, ForeignKey(User.id), nullable=False)
    note = db.Column(db.String(32), nullable=False)
    created_on = db.Column(db.Date, nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=False)

    user = relationship("User", back_populates="fingerprints", passive_deletes=True)
