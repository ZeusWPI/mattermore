from datetime import datetime
from flask import Blueprint
import requests

from app.app import mattermost_response


resto_blueprint = Blueprint("resto", __name__)


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


@resto_blueprint.route("/resto", methods=["GET"])
def resto_menu():
    today = datetime.today()
    url = f"https://hydra.ugent.be/api/2.0/resto/menu/nl/{today.year}/{today.month}/{today.day}.json"
    resto = requests.get(url, timeout=5).json()

    if not resto["open"]:
        return "De resto is vandaag gesloten."
    else:

        def table_for(kinds):
            items = [meal for meal in resto["meals"] if meal["kind"] in kinds]
            return format_items(items)

        def format_items(items):
            if not items:
                return "None :("
            maxwidth = max(len(item["name"]) for item in items)
            return "\n".join(
                "{name: <{width}}{price}".format(
                    name=item["name"], width=maxwidth + 2, price=item["price"]
                )
                for item in items
            )

        recognized_kinds = set.union(*RESTO_TABLES.values())
        uncategorized_meals = [
            meal for meal in resto["meals"] if meal["kind"] not in recognized_kinds
        ]

        uncategorized = (
            ""
            if not uncategorized_meals
            else UNCATEGORIZED_TEMPLATE.format(
                format_items(
                    [
                        # Small hack: change "name" into "name (kind)"
                        {**meal, "name": "{} ({})".format(meal["name"], meal["kind"])}
                        for meal in uncategorized_meals
                    ]
                )
            )
        )

        return RESTO_TEMPLATE.format(
            **{k: table_for(v) for k, v in RESTO_TABLES.items()},
            uncategorized=uncategorized,
            vegetable_table="\n".join(resto["vegetables"]),
        )


@resto_blueprint.route("/resto.json", methods=["GET"])
def resto_menu_json():
    return mattermost_response(resto_menu(), ephemeral=True)
