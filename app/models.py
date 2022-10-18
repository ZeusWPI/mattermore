from datetime import datetime
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
import re
import secrets
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from typing import Optional

from app.app import app

db = SQLAlchemy(app)
migrate = Migrate(app, db)

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


class BaseModel:
    def save(self):
        """Save this entity to the database"""

        db.session.add(self)
        db.session.commit()


class User(db.Model, BaseModel):
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
        """Generate a doorkey for the user"""

        self.doorkey = secrets.token_urlsafe(16)

    @classmethod
    def get_user_fingerprints(cls):
        """Get a list of all users and their corresponding fingerprints"""

        return db.session.query(cls, Fingerprint).join(Fingerprint).all()

    @classmethod
    def find_by_mm_id(cls, mm_id: int) -> Optional["User"]:
        """Find a user given their mattermost ID"""

        return db.session.query(cls).filter(cls.mattermost_id == mm_id).scalar()


class Quote(db.Model, BaseModel):
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


class KeyValue(db.Model, BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    keyname = db.Column(db.String(255), unique=True, nullable=False)
    value = db.Column(db.String(16383), unique=False, nullable=True)

    def __init__(self, keyname, value):
        super()
        self.keyname = keyname
        self.value = value

    def __repr__(self):
        return '<KeyValue {} = "{}">'.format(self.keyname, self.value)


class Fingerprint(db.Model, BaseModel):
    id = db.Column(db.Integer, nullable=False, unique=True, primary_key=True)
    user_id = db.Column(db.Integer, ForeignKey(User.id), nullable=False)
    note = db.Column(db.String(32), nullable=False)
    created_on = db.Column(db.Date, nullable=False)

    # When a new fingerprint is inserted the fingerprint is placed into enroll mode
    # it is perfectly possible that this process will fail, as such this field
    # is needed to indicate if a fingerprint has simply been inserted or if it
    # has been inserted and validated
    active = db.Column(db.Boolean, nullable=False, default=False)

    user = relationship("User", back_populates="fingerprints", passive_deletes=True)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}> id: {self.id} user_id: {self.user_id} note: {self.note} created_on: {self.created_on}"

    def __init__(self, id_: int, user_id: int, note: str, created_on: datetime):
        super()
        self.id = id_
        self.user_id = user_id
        self.note = note
        self.created_on = created_on

    @classmethod
    def create(cls, id_: int, user_id: int, note: str, created_on: datetime):
        db.session.add(cls(id_, user_id, note, created_on))
        db.session.commit()

    @classmethod
    def clear_inactive(cls):
        """Remove all inactive fingerprints"""

        fps = db.session.query(cls).filter(cls.active == False).all()

        for fp in fps:
            db.session.delete(fp)

        db.session.commit()

        return list(map(lambda f: f.id, fps))

    @classmethod
    def find(cls, user_id: int, note: str) -> Optional["Fingerprint"]:
        return (
            db.session.query(cls)
            .filter(cls.note == note, cls.user_id == user_id)
            .scalar()
        )

    @classmethod
    def find_by_id(cls, id_: int) -> Optional["Fingerprint"]:
        return db.session.query(cls).filter(cls.id == id_).scalar()

    @classmethod
    def find_active_by_id(cls, id_: int) -> Optional["Fingerprint"]:
        print(db.session.query(cls).all())
        return db.session.query(cls).filter(cls.id == id_, cls.active == True).scalar()

    def delete_(self):
        db.session.delete(self)
        db.session.commit()
