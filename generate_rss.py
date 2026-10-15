import json
import os
import re
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

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
    """ Construit une URL absolue propre en évitant les doublons de chemin """
    if not href:
        return None
    href = href.strip()
    if href.startswith('http://') or href.startswith('https://'):
        return href
    if not href.startswith('/'):
        href = '/' + href
    return urljoin(DOMAIN_BASE, href)

def extract_image(card, current_url):
    """ Cherche l'image dans la carte et construit une URL absolue correcte """
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

    for source in card.find_all('source'):
        srcset = source.get('srcset') or source.get('data-srcset')
        if srcset:
            src = srcset.split(',')[0].strip().split()[0]
            if src and not src.startswith('data:'):
                return clean_url(src)

    bg_elements = card.find_all(style=re.compile(r'background-image', re.I))
    if card.get('style') and 'background-image' in card.get('style').lower():
        bg_elements.append(card)

    for el in bg_elements:
        style = el.get('style', '')
        match = re.search(r'url\(([\'"]?)(.*?)\1\)', style, re.I)
        if match:
            bg_url = match.group(2).strip("'\"")
            if not bg_url.startswith('data:'):
                return clean_url(bg_url)

    return None

def is_agenda_item(card, href, title):
    """ Détermine si un élément appartient à l'agenda plutôt qu'aux news """
    href_lower = href.lower()
    
    if any(k in href_lower for k in ['/agenda', '/evenement', '/event', 'calendar']):
        return True
        
    card_html = str(card).lower()
    if 'k-card--event' in card_html or 'agenda' in card_html:
        if card.find(class_=re.compile(r'date|calendar|event', re.I)):
            return True

    return False

def build_rss():
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.9,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    print(f"Interrogation de {BASE_URL}...")
    response = session.get(BASE_URL, headers=headers, timeout=15)
    print(f"Code HTTP reçu : {response.status_code}")
    print(f"Taille de la réponse reçue : {len(response.content)} octets")
    response.raise_for_status()
    
    soup = BeautifulSoup(response.content, "html.parser")
    history = load_history()

    fg = FeedGenerator()
    fg.id(BASE_URL)
    fg.title("ULiège - Toutes les news")
    fg.author({'name': 'Université de Liège'})
    fg.link(href=BASE_URL, rel='alternate')
    fg.description("Flux RSS des actualités de l'Université de Liège")
    fg.language('fr')

    all_links = soup.find_all('a', href=True)
    print(f"DEBUG TOTAL : {len(all_links)} liens trouvés sur la page.")

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

        summary_text = ""
        p_tag = parent_container.find('p')
        if p_tag:
            p_text = p_tag.get_text(strip=True)
            if len(p_text) > 15 and p_text.lower() != title.lower():
                summary_text = p_text

        if not summary_text:
            summary_text = title

        if full_url in history:
            pub_date = datetime.fromisoformat(history[full_url])
        else:
            pub_date = datetime.now(timezone.utc)
