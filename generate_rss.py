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
    "international", "presse", "lire la suite", "en savoir plus", "en savoir +", "tous les événements", "voir l'agenda"
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

def fetch_page_html_with_playwright():
    print("Étape 3 : Lancement de Playwright en mode furtif...")
    from playwright.sync_api import sync_playwright
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-infobars',
                '--window-size=1920,1080',
                '--disable-dev-shm-usage'
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080},
            locale="fr-FR",
            java_script_enabled=True
        )
        page = context.new_page()
        
        # Masquer les indicateurs d'automatisation
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        try:
            print(f"Navigation vers {BASE_URL}...")
            # On utilise load au lieu de networkidle pour éviter les blocages de timeout sur les scripts analytics
            page.goto(BASE_URL, timeout=60000, wait_until="load")
            
            print("Attente de la résolution du challenge JavaScript anti-bot (10 secondes)...")
            page.wait_for_timeout(10000)
            
            # Simuler un scroll pour forcer le rendu des éléments si nécessaire
            page.evaluate("window.scrollBy(0, 600)")
            page.wait_for_timeout(3000)
            
            html_content = page.content()
            print(f"Taille du HTML décodé par le navigateur : {len(html_content)} octets")
            browser.close()
            return html_content
        except Exception as e:
            print(f"Erreur Playwright : {e}")
            browser.close()
            return ""

def build_rss():
    html_content = fetch_page_html_with_playwright()
    if not html_content:
        print("Erreur : Impossible de récupérer le HTML via Playwright.")
        return

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
    print(f"DEBUG : {len(all_links)} balises <a> trouvées après exécution du JavaScript.")

    seen_links = set()
    count = 0

    for link in all_links:
        href = link.get('href')
        full_url = clean_url(href)

        if not full_url or 'uliege.be' not in full_url:
            continue

        # Signature JCMS : Les articles possèdent un ID de type c_ suivi de chiffres
        if not re.search(r'/c_\d+/', full_url):
            continue

        if full_url.rstrip('/') == BASE_URL.rstrip('/'):
            continue

        if any(exc in full_url.lower() for exc in EXCLUDED_URL_PARTS):
            continue

        if full_url in seen_links:
            continue
        seen_links.add(full_url)

        title = link.get_text(strip=True)
        if not title or len(title) < 10:
            container = link.find_parent(['article', 'div', 'li', 'section'])
            if container:
                title_tag = container.find(['h1', 'h2', 'h3', 'h4', 'h5'])
                if title_tag:
                    title = title_tag.get_text(strip=True)

        if not title or len(title) < 10:
            path_parts = urlparse(full_url).path.split('/')
            slug = path_parts[-1] if path_parts else "Actualité ULiège"
            title = re.sub(r'[-_]', ' ', slug).capitalize()

        if any(exc in title.lower() for exc in EXCLUDED_EXACT_TITLES):
            continue

        if 'agenda' in full_url.lower() or 'evenement' in full_url.lower():
            continue

        if full_url in history:
            pub_date = datetime.fromisoformat(history[full_url])
        else:
            pub_date = datetime.now(timezone.utc)
            history[full_url] = pub_date.isoformat()

        description_html = f"<p>{title}</p>"

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
        print("Démarrage du script avec Playwright Stealth...")
        build_rss()
        print("Script exécuté avec succès !")
    except Exception as e:
        import traceback
        print("ERREUR FATALE DU SCRIPT :")
        traceback.print_exc()
        sys.exit(1)
