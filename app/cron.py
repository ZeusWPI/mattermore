from app import models
from app.app import db, mm_driver, config
from app.app import app
from flask import current_app
from flask_apscheduler import APScheduler
import atexit
import requests
from bs4 import BeautifulSoup

DICT_NEWS_KEY = 'dict_news'
STANDARD_HEADERS = {'User-Agent': 'Zeus-Scraper/1.0 (+https://zeus.ugent.be/contact/)'}

DICT_NEWS_URL_BASE = 'https://helpdesk.ugent.be/nieuws/'

scheduler = APScheduler()


def get_dict_news():
    r = requests.get(DICT_NEWS_URL_BASE, headers=STANDARD_HEADERS)
    soup = BeautifulSoup(r.text, 'html.parser')
    result = []
    for table in soup.find_all('table', ['table-newsoverview']):
        for row in table.find_all('tr'):
            date = row.find('td', ['date']).find('span').text
            link_element = row.find('a')
            link_id = int(link_element.get('href').split('?id=')[-1])
            link = DICT_NEWS_URL_BASE + link_element.get('href')
            message = link_element.text
            result.append({'id': link_id, 'date': date, 'message': message, 'link': link})
    return result



def post_dict_news(n):
    message = f'**DICT NIEUWS** op {n["date"]}: [{n["message"]}]({n["link"]})'
    print(f"Posting {message}")
    mm_driver.posts.create_post(options={
                'channel_id': config.sysadmin_channel_id,
                'message': message
    })


@scheduler.task('interval', id='dict_news_task', minutes=5)
def dict_news_task():
    with app.app_context():
        dict_config = models.KeyValue.query.filter_by(keyname=DICT_NEWS_KEY).first() or models.KeyValue(DICT_NEWS_KEY, "111")
        news_items = get_dict_news()
        db_maxseen = int(dict_config.value)
        current_maxseen = db_maxseen
        for news_item in get_dict_news():
            current_maxseen = max(current_maxseen, news_item['id'])
            if news_item['id'] > db_maxseen:
                post_dict_news(news_item)
        dict_config.value = str(current_maxseen)
        db.session.add(dict_config)
        db.session.commit()


scheduler.api_enabled = True
scheduler.init_app(app)
scheduler.start()
