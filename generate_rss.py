import sys
import json
import os
import re

print("Étape 1 : Modules de base importés.")

from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

print("Étape 2 : BeautifulSoup et FeedGenerator importés.")

BASE_URL = "https://www.news.uliege.be/cms/c_9435330/fr/portail-news-agendas-toutes-les-news"
DOMAIN_BASE = "https://www.news.uliege.be"
HISTORY_FILE = "history.json"

EXCLUDED_EXACT_TITLES = [
    "labels et accréditations",
    "s'informer",
    "médias de l'uliège",
    "grandes conférences universitaires",
    "facultés et instituts",
    "études",
    "recherche",
    "agenda",
    "portail news",
    "toutes les news",
    "voir le documentaire",
    "recherche & innovation",
    "l'université de liège",
    "news & agendas",
    "international",
    "presse",
    "lire la suite",
    "en savoir plus",
    "en savoir +",
    "tous les événements",
    "voir l'agenda"
]

EXCLUDED_URL_PARTS = [
    '/labels', '/s-informer', '/medias', '/conferences', '/annuaire', 
    '/facultes', '/etudes', '/recherche', '/agenda', '/contact', 
    '/plan', '/mentions-legales', '/credits', '/accessibilite',
    '/portail', '/navigation', '/footer', '/menu'
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
    print("Étape 3 : Importation de Playwright et interception réseau...")
    from playwright.sync_api import sync_playwright
    
    intercepted_data = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        
        # Intercepter les réponses du réseau pour capturer les flux JSON ou HTML utiles
        def handle_response(response):
            try:
                if '/cms/' in response.url and response.status == 200:
                    ct = response.headers.get('content-type', '')
                    if 'json' in ct or 'html' in ct:
                        body = response.text()
                        if len(body) > 2000: # On cherche un contenu d'articles conséquent
                            intercepted_data.append(body)
            except Exception:
                pass

        page.on("response", handle_response)
        
        try:
            page.goto(BASE_URL, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(8000) # Laisser le temps aux requêtes AJAX de passer
        except Exception as e:
            print(f"Erreur lors du chargement : {e}")

        browser.close()
        
        # Si on a capturé du contenu riche via le réseau, on l'utilise, sinon on renvoie le HTML classique
        if intercepted_data:
            print(f"Succès : {len(intercepted_data)} flux de données interceptés via le réseau !")
            return intercepted_data[-1] # On prend le dernier bloc de données le plus complet
        
        return page.content()

def build_rss():
    html_content = fetch_page_html()
    print(f"Taille finale du HTML traité : {len(html_content)} octets")
    
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
    print(f"DEBUG : {len(all_links)} liens totaux trouvés sur la page.")

    seen_links = set()
    count = 0

    for link in all_links:
        href = link.get('href')
        full_url = clean_url(href)

        if not full_url or 'uliege.be' not in full_url or '/cms/' not in full_url:
            continue

        if any(exc in full_url.lower() for exc in EXCLUDED_URL_PARTS):
            continue

        if link.find_parent(['nav', 'header', 'footer', 'aside']):
            continue

        container = link.find_parent(['article', 'div', 'li', 'section']) or link

        parent_classes = " ".join([str(cls) for p in link.parents for cls in p.get('class', [])]).lower()
        if any(term in parent_classes for term in ['menu', 'nav', 'breadcrumb', 'footer', 'header', 'facette', 'filter']):
            continue

        title = link.get_text(strip=True)
        if not title or len(title) < 15:
            title_tag = container.find(['h1', 'h2', 'h3', 'h4', 'h5'])
            if title_tag:
                title = title_tag.get_text(strip=True)

        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if any(exc in title_lower for exc in EXCLUDED_EXACT_TITLES):
            continue

        if is_agenda_item(container, href, title):
            continue

        if full_url in seen_links:
            container_is_new = False
        else:
            seen_links.add(full_url)

        image_url = extract_image(container, full_url)
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
        print("Démarrage du script principal...")
        build_rss()
        print("Script exécuté avec succès !")
    except Exception as e:
        import traceback
        print("ERREUR FATALE DANS LE SCRIPT :")
        traceback.print_exc()
        sys.exit(1)
