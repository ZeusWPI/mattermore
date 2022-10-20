from flask import Blueprint, request
import random

from app import models
from app.util import mattermost_response, requires_token

quote_blueprint = Blueprint("quote", __name__)


@quote_blueprint.route("/addquote", methods=["POST"])
@requires_token("quote")
def add_quote():
    user = request.values["user_name"]
    channel = request.values["channel_name"]
    quote_text = request.values["text"]
    quote = models.Quote(user, quote_text, channel)
    quote.save()

    return mattermost_response('{} added the quote "{}"'.format(user, quote_text))


@quote_blueprint.route("/quote", methods=["POST"])
def random_quote():
    text_contains = request.values["text"]
    matches = models.Quote.query.filter(
        models.Quote.quote.contains(text_contains)
    ).all()
    if matches:
        selected_quote = random.choice(matches)
        response = selected_quote.quote
        return mattermost_response(response)
    return mattermost_response(
        'No quotes found matching "{}"'.format(text_contains), ephemeral=True
    )
