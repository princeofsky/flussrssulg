import json
import os
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
from urllib.parse import urljoin

BASE_URL = "https://www.news.uliege.be/cms/c_9435330/fr/portail-news-agendas-toutes-les-news"
HISTORY_FILE = "history.json"

EXCLUDED_TITLES = [
    "voir le documentaire",
    "recherche & innovation",
    "l'université de liège",
    "news & agendas",
    "international",
    "toutes les news",
    "agenda",
    "presse"
]

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def build_rss():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    response = requests.get(BASE_URL, headers=headers, timeout=15)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.content, "html.parser")
    history = load_history()
    now_iso = datetime.now(timezone.utc).isoformat()

    fg = FeedGenerator()
    fg.id(BASE_URL)
    fg.title("ULiège - Toutes les news")
    fg.author({'name': 'Université de Liège'})
    fg.link(href=BASE_URL, rel='alternate')
    fg.description("Flux RSS des actualités de l'Université de Liège")
    fg.language('fr')

    articles_blocks = soup.select('.k-card, .k-tile, article, .news-item, .fiche-summary, .content-list-item')
    
    if not articles_blocks:
        main_content = soup.find('main') or soup.find('div', id='content') or soup
        articles_blocks = main_content.find_all(['div', 'article', 'li'])

    seen_links = set()
    count = 0

    for block in articles_blocks:
        link_tag = block.find('a', href=True) if block.name != 'a' else block
        
        if not link_tag or not link_tag.get('href'):
            continue

        title = link_tag.get_text(strip=True)
        href = link_tag['href']

        if not title or len(title) < 15 or title.lower() in EXCLUDED_TITLES:
            continue

        if not ('/cms/c_' in href or '/news/' in href):
            continue

        full_url = urljoin(BASE_URL, href)

        if full_url in seen_links:
            continue
        seen_links.add(full_url)

        # Attribuer une date fixe si l'article a déjà été vu
        if full_url in history:
            pub_date = datetime.fromisoformat(history[full_url])
        else:
            pub_date = datetime.now(timezone.utc)
            history[full_url] = pub_date.isoformat()

        # Image
        image_url = None
        img_tag = block.find('img')
        if img_tag and img_tag.get('src'):
            src = img_tag.get('src') or img_tag.get('data-src')
            if src and not src.startswith('data:'):
                image_url = urljoin(BASE_URL, src)

        # Résumé
        summary_text = title
        p_tag = block.find('p')
        if p_tag and len(p_tag.get_text(strip=True)) > 20:
            summary_text = p_tag.get_text(strip=True)

        description_html = ""
        if image_url:
            description_html += f'<p><img src="{image_url}" alt="{title}" style="max-width:100%; height:auto;" /></p>'
        description_html += f'<p>{summary_text}</p>'

        fe = fg.add_entry()
        fe.id(full_url)
        fe.title(title)
        fe.link(href=full_url)
        fe.description(description_html)
        fe.pubDate(pub_date)

        if image_url:
            fe.enclosure(image_url, 0, 'image/jpeg')

        count += 1
        if count >= 30:
            break

    save_history(history)
    fg.rss_file('feed.xml')
    print(f"Flux mis à jour : {count} articles valides enregistrés.")

if __name__ == '__main__':
    build_rss()
