from .app import db


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
