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
    "labels et accréditations", "s'informer", "médias de l'uliège", "grandes conférences universitaires",
    "facultés et instituts", "études", "recherche", "agenda", "portail news", "toutes les news",
    "voir le documentaire", "recherche & innovation", "l'université de liège", "news & agendas",
    "international", "presse", "lire la suite", "en savoir plus", "en savoir +", "tous los événements", "voir l'agenda"
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

def fetch_page_data():
    print("Étape 3 : Importation de Playwright et interception réseau...")
    from playwright.sync_api import sync_playwright
    
    intercepted_payloads = []

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
        
        def handle_response(response):
            try:
                # On cherche les requêtes qui retournent du contenu en lien avec les cms ou listes
                if ('/cms/' in response.url or 'json' in response.headers.get('content-type', '')) and response.status == 200:
                    body = response.text()
                    if len(body) > 500:
                        intercepted_payloads.append((response.url, response.headers.get('content-type', ''), body))
            except Exception:
                pass

        page.on("response", handle_response)
        
        try:
            page.goto(BASE_URL, timeout=45000, wait_until="networkidle")
            page.wait_for_timeout(6000)
        except Exception as e:
            print(f"Erreur lors du chargement : {e}")

        browser.close()
        return intercepted_payloads

def build_rss():
    payloads = fetch_page_data()
    print(f"Nombre de flux réseau interceptés : {len(payloads)}")
    
    history = load_history()
    fg = FeedGenerator()
    fg.id(BASE_URL)
    fg.title("ULiège - Toutes les news")
    fg.author({'name': 'Université de Liège'})
    fg.link(href=BASE_URL, rel='alternate')
    fg.description("Flux RSS des actualités de l'Université de Liège")
    fg.language('fr')

    count = 0
    seen_links = set()

    # Analyse des payloads interceptés
    for url, content_type, body in payloads:
        print(f"Inspection de l'URL interceptée : {url} (Type: {content_type})")
        
        # Si c'est du JSON, on peut tenter d'extraire des structures d'articles
        if 'json' in content_type.lower():
            try:
                data = json.loads(body)
                print(" -> Format JSON détecté. (Affichage partiel pour debug si besoin)")
                # Si le JSON contient une liste d'articles, on pourra les parser ici
            except json.JSONDecodeError:
                pass

        # Si c'est du HTML, on le parse avec BeautifulSoup comme avant
        if 'html' in content_type.lower() or '<html' in body.lower():
            soup = BeautifulSoup(body, "html.parser")
            all_links = soup.find_all('a', href=True)
            print(f" -> HTML détecté : {len(all_links)} liens trouvés dans ce flux.")

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
                title = link.get_text(strip=True)
                if not title or len(title) < 15:
                    title_tag = container.find(['h1', 'h2', 'h3', 'h4', 'h5'])
                    if title_tag:
                        title = title_tag.get_text(strip=True)

                if not title or len(title) < 15 or any(exc in title.lower() for exc in EXCLUDED_EXACT_TITLES):
                    continue

                if full_url in seen_links:
                    continue
                seen_links.add(full_url)

                if full_url in history:
                    pub_date = datetime.fromisoformat(history[full_url])
                else:
                    pub_date = datetime.now(timezone.utc)
                    history[full_url] = pub_date.isoformat()

                fe = fg.add_entry()
                fe.id(full_url)
                fe.title(title)
                fe.link(href=full_url)
                fe.description(f"<p>{title}</p>")
                fe.pubDate(pub_date)

                count += 1
                if count >= 35:
                    break

    save_history(history)
    fg.rss_file('feed.xml')
    print(f"Flux mis à jour : {count} articles valides enregistrés.")

if __name__ == '__main__':
    try:
        print("Démarrage du script avec analyse des flux réseau...")
        build_rss()
        print("Script exécuté avec succès !")
    except Exception as e:
        import traceback
        print("ERREUR FATALE DANS LE SCRIPT :")
        traceback.print_exc()
        sys.exit(1)
