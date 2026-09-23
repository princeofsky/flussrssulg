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
    # 1. Recherche dans les balises <img>
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

    # 2. Recherche dans les balises <picture> / <source>
    for source in card.find_all('source'):
        srcset = source.get('srcset') or source.get('data-srcset')
        if srcset:
            src = srcset.split(',')[0].strip().split()[0]
            if src and not src.startswith('data:'):
                return clean_url(src)

    # 3. Recherche dans les styles d'arrière-plan CSS
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
    
    # Check URL
    if any(k in href_lower for k in ['/agenda', '/evenement', '/event', 'calendar']):
        return True
        
    # Check classes et contenu texte du conteneur
    card_html = str(card).lower()

    if 'k-card--event' in card_html or 'agenda' in card_html:
        if card.find(class_=re.compile(r'date|calendar|event', re.I)):
            return True

    return False

def build_rss():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    response = requests.get(BASE_URL, headers=headers, timeout=15)
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

    main_content = soup.find('main') or soup.find('div', id='content') or soup

    # Sélection ciblée des cartes d'articles
    cards = main_content.select(
        '.k-card, .k-tile, article, .fiche-summary, .content-list-item, '
        '[class*="k-card"], [class*="card"]'
    )

    seen_links = set()
    count = 0

    for card in cards:
        # Éviter les conteneurs parents englobants si une sous-carte existe
        if card.select('.k-card, .k-tile, article'):
            continue

        # Extraction prioritaire du titre et du lien directement liés
        title_tag = card.find(['h1', 'h2', 'h3', 'h4', 'h5']) or card.find(class_=re.compile(r'title', re.I))
        
        link_tag = None
        if title_tag:
            link_tag = title_tag.find('a', href=True) or title_tag.find_parent('a', href=True)
            
        if not link_tag:
            link_tag = card.find('a', href=True)

        if not link_tag:
            continue

        href = link_tag['href']
        
        # Ignorer les ancres, javascripts ou liens vides
        if not href or href.startswith('#') or href.startswith('javascript:'):
            continue

        full_url = clean_url(href)

        # Éliminer les domaines externes (ex. réseaux sociaux)
        if not full_url or 'uliege.be' not in full_url:
            continue

        # Extraction du texte du titre
        title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)

        if not title or len(title) < 10 or title.lower() in EXCLUDED_TITLES:
            continue

        # Vérification si c'est un événement d'agenda
        if is_agenda_item(card, href, title):
            continue

        # Dédoublonnage
        if full_url in seen_links:
            continue
        seen_links.add(full_url)

        # Extraction de l'image
        image_url = extract_image(card, full_url)

        # Extraction du résumé
        summary_text = ""
        p_tag = card.find('p')
        if p_tag:
            p_text = p_tag.get_text(strip=True)
            if len(p_text) > 15 and p_text.lower() != title.lower():
                summary_text = p_text

        if not summary_text:
            summary_text = title

        # Date stable via history.json
        if full_url in history:
            pub_date = datetime.fromisoformat(history[full_url])
        else:
            pub_date = datetime.now(timezone.utc)
            history[full_url] = pub_date.isoformat()

        # Construction du HTML de l'entrée RSS
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
        if count >= 35:
            break

    save_history(history)
    fg.rss_file('feed.xml')
    print(f"Flux mis à jour : {count} articles valides enregistrés.")

if __name__ == '__main__':
    build_rss()
