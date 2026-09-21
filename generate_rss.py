import json
import os
import re
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
    "presse",
    "lire la suite",
    "en savoir plus"
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

def extract_image_from_card(card):
    """ Extrait l'URL de l'image d'un bloc carte (balises <img>, lazy loading, ou style CSS) """
    if not card:
        return None

    # 1. Chercher toutes les balises <img> dans la carte
    for img in card.find_all('img'):
        # Tester tous les attributs de source possibles
        src = (
            img.get('src') or 
            img.get('data-src') or 
            img.get('data-lazy-src') or 
            img.get('data-original')
        )
        
        # Gestion des attributs srcset / data-srcset
        if not src:
            srcset = img.get('srcset') or img.get('data-srcset')
            if srcset:
                src = srcset.split(',')[0].strip().split()[0]

        if src and not src.startswith('data:'):
            return src

    # 2. Chercher dans les balises <picture> / <source>
    for source in card.find_all('source'):
        srcset = source.get('srcset') or source.get('data-srcset')
        if srcset:
            src = srcset.split(',')[0].strip().split()[0]
            if src and not src.startswith('data:'):
                return src

    # 3. Chercher dans les styles CSS d'arrière-plan
    bg_elements = card.find_all(style=re.compile(r'background-image', re.I))
    if card.get('style') and 'background-image' in card.get('style').lower():
        bg_elements.append(card)

    for el in bg_elements:
        style = el.get('style', '')
        match = re.search(r'url\(([\'"]?)(.*?)\1\)', style, re.I)
        if match:
            bg_url = match.group(2)
            if not bg_url.startswith('data:'):
                return bg_url

    return None

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

    # Sélection de tous les conteneurs d'articles possibles (y compris la Une)
    cards = main_content.select(
        '.k-card, .k-tile, article, .news-item, .fiche-summary, '
        '.content-list-item, .featured-news, .news-featured, .k-card-featured, '
        '[class*="card"], [class*="tile"], [class*="item"]'
    )

    seen_links = set()
    count = 0

    for card in cards:
        # Trouver le lien principal de la carte
        link_tag = card.find('a', href=True)
        if not link_tag:
            continue

        href = link_tag['href']

        # Filtre sur le format d'URL d'un article ULiège
        if not ('/cms/c_' in href or '/news/' in href):
            continue

        full_url = urljoin(BASE_URL, href)

        if full_url in seen_links or '#' in href:
            continue

        # Récupérer le titre (dans un header si présent, sinon le texte du lien)
        title_tag = card.find(['h1', 'h2', 'h3', 'h4', 'h5', '.title', '.k-card__title'])
        if title_tag:
            title = title_tag.get_text(strip=True)
        else:
            title = link_tag.get_text(strip=True)

        if not title or len(title) < 10 or title.lower() in EXCLUDED_TITLES:
            continue

        seen_links.add(full_url)

        # Extraction de l'image
        raw_image_url = extract_image_from_card(card)
        image_url = urljoin(BASE_URL, raw_image_url) if raw_image_url else None

        # Extraction du résumé
        summary_text = title
        p_tag = card.find('p')
        if p_tag and len(p_tag.get_text(strip=True)) > 15:
            summary_text = p_tag.get_text(strip=True)

        # Gestion de l'historique de date
        if full_url in history:
            pub_date = datetime.fromisoformat(history[full_url])
        else:
            pub_date = datetime.now(timezone.utc)
            history[full_url] = pub_date.isoformat()

        # Construction de l'entrée RSS
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
