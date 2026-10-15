import sys
import json
import os
import re
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.news.uliege.be/cms/c_9435330/fr/portail-news-agendas-toutes-les-news"
DOMAIN_BASE = "https://www.news.uliege.be"
HISTORY_FILE = "history.json"

EXCLUDED_TITLES = [
    "voir le documentaire",
    "recherche & innovation",
    "l'université de liège",
    "news & agendas",
    "international",
    "toutes les news",
    "agenda",
    "presse",
    "lire la suite",
    "en savoir plus",
    "en savoir +",
    "tous les événements",
    "voir l'agenda"
]

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def clean_url(href):
    if not href:
        return None
    href = href.strip()
    if href.startswith('http://') or href.startswith('https://'):
        return href
    if not href.startswith('/'):
        href = '/' + href
    return urljoin(DOMAIN_BASE, href)

def extract_image(card, current_url):
    for img in card.find_all('img'):
        src = (
            img.get('src') or 
            img.get('data-src') or 
            img.get('data-lazy-src') or 
            img.get('data-original')
        )
        if not src and img.get('srcset'):
            src = img.get('srcset').split(',')[0].strip().split()[0]
        if src and not src.startswith('data:'):
            return clean_url(src)
    return None

def is_agenda_item(card, href, title):
    href_lower = href.lower()
    if any(k in href_lower for k in ['/agenda', '/evenement', '/event', 'calendar']):
        return True
    return False

def fetch_page_html():
    """ Utilise Playwright pour charger la page et exécuter le JavaScript """
    print(f"Lancement de Playwright pour interroger {BASE_URL}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        page.goto(BASE_URL, timeout=45000)
        
        # On attend un court instant que les éléments dynamiques/JS finissent de s'injecter
        print("Attente du chargement complet du contenu JavaScript...")
        page.wait_for_timeout(4000)
        
        html_content = page.content()
        browser.close()
        return html_content

def build_rss():
    html_content = fetch_page_html()
    print(f"Taille du HTML récupéré via Playwright : {len(html_content)} octets")
    
    soup = BeautifulSoup(html_content, "html.parser")
    history = load_history()

    fg = FeedGenerator()
    fg.id(BASE_URL)
    fg.title("ULiège - Toutes les news")
    fg.author({'name': 'Université de Liège'})
    fg.link(href=BASE_URL, rel='alternate')
    fg.description("Flux RSS des actualités de l'Université de Liège")
    fg.language('fr')

    all_links = soup.find_all('a', href=True)
    print(f"DEBUG TOTAL : {len(all_links)} liens trouvés sur la page après rendu JS.")

    seen_links = set()
    count = 0

    for link in all_links:
        href = link.get('href')
        if not href or href.startswith('#') or href.startswith('javascript:'):
            continue

        full_url = clean_url(href)

        if not full_url or 'uliege.be' not in full_url or '/cms/' not in full_url:
            continue

        title = link.get_text(strip=True)
        if not title or len(title) < 10:
            parent = link.find_parent(['article', 'div', 'li', 'p'])
            if parent:
                t_tag = parent.find(['h1', 'h2', 'h3', 'h4', 'h5'])
                if t_tag:
                    title = t_tag.get_text(strip=True)

        if not title or len(title) < 10 or title.lower() in EXCLUDED_TITLES:
            continue

        parent_container = link.find_parent(['article', 'div', 'li']) or link
        if is_agenda_item(parent_container, href, title):
            continue

        if full_url in seen_links:
            continue
        seen_links.add(full_url)

        image_url = extract_image(parent_container, full_url)
        summary_text = title

        if full_url in history:
            pub_date = datetime.fromisoformat(history[full_url])
        else:
            pub_date = datetime.now(timezone.utc)
            history[full_url] = pub_date.isoformat()

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

        count += 1
        if count >= 35:
            break

    save_history(history)
    fg.rss_file('feed.xml')
    print(f"Flux mis à jour : {count} articles valides enregistrés.")

if __name__ == '__main__':
    try:
        print("Démarrage du script Playwright...")
        build_rss()
        print("Script exécuté avec succès !")
    except Exception as e:
        import traceback
        print("ERREUR FATALE DANS LE SCRIPT :")
        traceback.print_exc()
        sys.exit(1)
