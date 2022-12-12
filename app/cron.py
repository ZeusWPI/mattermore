from app import models
from app.app import mm_driver, config
from app.app import app
from flask import current_app
from flask_apscheduler import APScheduler
import atexit
import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta

DICT_NEWS_KEY = "dict_news"
STANDARD_HEADERS = {"User-Agent": "Zeus-Scraper/1.0 (+https://zeus.ugent.be/contact/)"}

DICT_NEWS_URL_BASE = "https://helpdesk.ugent.be/nieuws/"

HYDRA_API_RESTO_BASE = "https://hydra.ugent.be/api/2.0/resto/menu/nl/"

scheduler = APScheduler()


def get_dict_news():
    r = requests.get(DICT_NEWS_URL_BASE, headers=STANDARD_HEADERS)
    soup = BeautifulSoup(r.text, "html.parser")
    result = []
    for table in soup.find_all("table", ["table-newsoverview"]):
        for row in table.find_all("tr"):
            date = row.find("td", ["date"]).find("span").text
            link_element = row.find("a")
            link_id = int(link_element.get("href").split("?id=")[-1])
            link = DICT_NEWS_URL_BASE + link_element.get("href")
            message = link_element.text
            result.append(
                {"id": link_id, "date": date, "message": message, "link": link}
            )
    return result


def post_dict_news(n):
    message = f'**DICT NIEUWS** op {n["date"]}: [{n["message"]}]({n["link"]})'
    print(f"Posting {message}")
    mm_driver.posts.create_post(
        options={"channel_id": config.sysadmin_channel_id, "message": message}
    )


@scheduler.task("interval", id="dict_news_task", minutes=5)
def dict_news_task():
    with app.app_context():
        dict_config = models.KeyValue.query.filter_by(
            keyname=DICT_NEWS_KEY
        ).first() or models.KeyValue(DICT_NEWS_KEY, "111")
        news_items = get_dict_news()
        current_maxseen = int(dict_config.value)
        for news_item in get_dict_news():
            if news_item["id"] > current_maxseen:
                current_maxseen = news_item["id"]
                post_dict_news(news_item)
        dict_config.value = str(current_maxseen)
        dict_config.save()


def render_menu(menu_json):
    rendered = f"#### Menu voor {menu_json['date']}\n"

    render_item = lambda i: f" - {i['name']}"

    soups = "\n".join(
        map(
            render_item,
            filter(lambda m: m["kind"] == "soup", menu_json["meals"]),
        )
    )
    mains = "\n".join(
        map(
            render_item,
            filter(lambda m: m["type"] == "main", menu_json["meals"]),
        )
    )
    colds = "\n".join(
        map(
            render_item,
            filter(lambda m: m["type"] == "cold", menu_json["meals"]),
        )
    )

    rendered += f"##### Soep\n{soups}\n##### Hoofdgerecht\n{mains}\n##### Koud\n{colds}"
    return rendered


@scheduler.task("cron", id="resto_menu_task", hour=4)
def resto_menu_task():
    today = date.today()
    today_url = f"{HYDRA_API_RESTO_BASE}{today.year}/{today.month}/{today.day}.json"
    try:
        today_json = requests.get(today_url).json()
    except:
        today_json = None

    tomorrow = today + timedelta(days=1)
    tomorrow_url = (
        f"{HYDRA_API_RESTO_BASE}{tomorrow.year}/{tomorrow.month}/{tomorrow.day}.json"
    )
    try:
        tomorrow_json = requests.get(tomorrow_url).json()
    except:
        tomorrow_json = None

    today_repr = render_menu(today_json) if today_json is not None else ""
    tomorrow_repr = render_menu(tomorrow_json) if tomorrow_json is not None else ""

    if (today_json is not None) or (tomorrow_json is not None):
        requests.post(
            config.resto_voedsels_webhook,
            json={"text": "\n\n".join([today_repr, tomorrow_repr])},
        )


scheduler.api_enabled = True
scheduler.init_app(app)
scheduler.start()
