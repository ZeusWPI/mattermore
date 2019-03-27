#!/usr/bin/env python3

from flask import Flask, request, Response, abort, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from app import models
from datetime import datetime
import config


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = config.DATABASE_URL
db = SQLAlchemy(app)

for line in open('quotes.tsv'):
    split = line.split("\t")
    assert len(split) == 4, "Too much tabs at line \"{}\", {}".format(line, len(split))
    quoter, channel, quote_text, created_at = split
    quote = models.Quote(quoter, quote_text, channel, created_at = datetime.strptime(created_at.strip(), "%Y-%m-%d %H:%M:%S"))
    db.session.add(quote)
db.session.commit()

