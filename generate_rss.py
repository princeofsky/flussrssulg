import sys
import json
import os
import re

print("Étape 1 : Modules de base importés.")

from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
import urllib.request

print("Étape 2 : FeedGenerator et urllib importés.")

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
    '/portail', '/navigation', '/footer', '/menu', '/agenda-'
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

def fetch_page_html():
    print(f"Interrogation de {BASE_URL} via urllib...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    }
    req = urllib.request.Request(BASE_URL, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            html_content = response.read().decode('utf-8', errors='ignore')
            print(f"Statut HTTP : {response.status}")
            return html_content
    except Exception as e:
        print(f"Erreur lors de la requête HTTP : {e}")
        return ""

def build_rss():
    html_content = fetch_page_html()
    print(f"Taille du HTML récupéré : {len(html_content)} octets")
    
    history = load_history()
    fg = FeedGenerator()
    fg.id(BASE_URL)
    fg.title("ULiège - Toutes les news")
    fg.author({'name': 'Université de Liège'})
    fg.link(href=BASE_URL, rel='alternate')
    fg.description("Flux RSS des actualités de l'Université de Liège")
    fg.language('fr')

    # Recherche large de tous les liens de type /fr/ ou /cms/ dans le code source de la page
    raw_matches = re.findall(r'["\'](/cms/[^"\']+)["\']', html_content)
    print(f"DEBUG : {len(raw_matches)} correspondances brutes trouvées commençant par /cms/.")
    
    # Affichons un petit échantillon (les 10 premiers) dans les logs pour voir à quoi ils ressemblent
    for sample in raw_matches[:10]:
        print(f"  -> Échantillon URL trouvée : {sample}")

    seen_links = set()
    count = 0

    for path in raw_matches:
        full_url = clean_url(path)

        if not full_url or 'uliege.be' not in full_url:
            continue

        if full_url.rstrip('/') == BASE_URL.rstrip('/'):
            continue

        if any(exc in full_url.lower() for exc in EXCLUDED_URL_PARTS):
            continue

        if full_url in seen_links:
            continue
        seen_links.add(full_url)

        # Génération d'un titre propre basé sur le slug de l'URL
        path_parts = urlparse(full_url).path.split('/')
        slug = path_parts[-1] if path_parts else "Actualité ULiège"
        title = re.sub(r'[-_]', ' ', slug).capitalize()

        if len(title) < 8 or any(exc in title.lower() for exc in EXCLUDED_EXACT_TITLES):
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
        print("Démarrage du script avec analyse des chemins /cms/...")
        build_rss()
        print("Script exécuté avec succès !")
    except Exception as e:
        import traceback
        print("ERREUR FATALE DU SCRIPT :")
        traceback.print_exc()
        sys.exit(1)
