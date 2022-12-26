#!/usr/bin/env python3

from app import models
from app.models import db
import app

with app.app.app_context():
    db.create_all()

    exists = models.User.query.filter_by(username="admin").first()
    if not exists:
        db.session.add(models.User("admin", admin=True))
        db.session.commit()
