#!/usr/bin/env python3

from app.app import db, models

db.create_all()

db.session.add(models.User('admin', admin=True))
db.session.commit()
