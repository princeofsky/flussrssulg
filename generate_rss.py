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
    "en savoir plus",
    "en savoir +"
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

def extract_image_from_container(container):
    """ Cherche l'image de l'article (img, srcset, lazy loading, picture ou background-image) """
    if not container:
        return None

    # 1. Balises <img>
    for img in container.find_all('img'):
        src = (
            img.get('src') or 
            img.get('data-src') or 
            img.get('data-lazy-src') or 
            img.get('data-original')
        )
        if not src:
            srcset = img.get('srcset') or img.get('data-srcset')
            if srcset:
                src = srcset.split(',')[0].strip().split()[0]

        if src and not src.startswith('data:'):
            return src

    # 2. Balises <picture> / <source>
    for source in container.find_all('source'):
        srcset = source.get('srcset') or source.get('data-srcset')
        if srcset:
            src = srcset.split(',')[0].strip().split()[0]
            if src and not src.startswith('data:'):
                return src

    # 3. Arrière-plan CSS
    bg_elements = container.find_all(style=re.compile(r'background-image', re.I))
    if container.get('style') and 'background-image' in container.get('style').lower():
        bg_elements.append(container)

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

    # On récupère TOUS les liens du bloc principal
    all_links = main_content.find_all('a', href=True)

    seen_links = set()
    count = 0

    for link in all_links:
        href = link['href']

        # 1. Filtre strict : doit être une actualité CMS et NE PAS être un événement/agenda
        if not ('/cms/c_' in href or '/news/' in href):
            continue
        
        # Exclusion explicite des liens de type Agenda/Événements
        if '/agenda' in href.lower() or '/evenement' in href.lower():
            continue

        full_url = urljoin(BASE_URL, href)

        if full_url in seen_links or '#' in href:
            continue

        # 2. Trouver la carte/conteneur le plus proche entourant ce lien
        card = link.find_parent(['article', 'li'])
        if not card:
            # Chercher un div avec une classe significative
            card = link.find_parent('div', class_=lambda c: c and any(k in c for k in ['card', 'tile', 'item', 'summary', 'block', 'news']))
        if not card:
            card = link.find_parent('div') or link

        # Vérifier si la carte elle-même est dans un bloc dédié à l'agenda
        card_classes = " ".join(card.get('class', [])).lower() if isinstance(card.get('class'), list) else str(card.get('class', '')).lower()
        if 'agenda' in card_classes or 'event' in card_classes:
            continue

        # 3. Extraction du titre (priorité à un titre h1-h5 ou classe .title dans la carte)
        title_tag = card.find(['h1', 'h2', 'h3', 'h4', 'h5']) or card.find(class_=re.compile(r'title', re.I))
        if title_tag:
            title = title_tag.get_text(strip=True)
        else:
            title = link.get_text(strip=True)

        if not title or len(title) < 12 or title.lower() in EXCLUDED_TITLES:
            continue

        seen_links.add(full_url)

        # 4. Extraction de l'image dans le conteneur (ou parents proches si besoin)
        raw_image_url = extract_image_from_container(card)
        if not raw_image_url and card.parent:
            raw_image_url = extract_image_from_container(card.parent)

        image_url = urljoin(BASE_URL, raw_image_url) if raw_image_url else None

        # 5. Extraction du résumé
        summary_text = title
        p_tag = card.find('p')
        if p_tag and len(p_tag.get_text(strip=True)) > 15:
            summary_text = p_tag.get_text(strip=True)

        # 6. Gestion de la date dans l'historique
        if full_url in history:
            pub_date = datetime.fromisoformat(history[full_url])
        else:
            pub_date = datetime.now(timezone.utc)
            history[full_url] = pub_date.isoformat()

        # 7. Création de l'entrée RSS
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
        if count >= 35: # Limite poussée à 35 articles
            break

    save_history(history)
    fg.rss_file('feed.xml')
    print(f"Flux mis à jour : {count} articles valides enregistrés.")

if __name__ == '__main__':
    build_rss()
