import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
from urllib.parse import urljoin

BASE_URL = "https://www.news.uliege.be/cms/c_9435330/fr/portail-news-agendas-toutes-les-news"

# Mots-clés / titres de menus à exclure explicitement
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

def build_rss():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    response = requests.get(BASE_URL, headers=headers, timeout=15)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.content, "html.parser")

    fg = FeedGenerator()
    fg.id(BASE_URL)
    fg.title("ULiège - Toutes les news")
    fg.author({'name': 'Université de Liège'})
    fg.link(href=BASE_URL, rel='alternate')
    fg.description("Flux RSS des actualités de l'Université de Liège")
    fg.language('fr')

    # Ciblage préférentiel des blocs d'articles (hors navigation/menus)
    articles_blocks = soup.select('.k-card, .k-tile, article, .news-item, .fiche-summary, .content-list-item')
    
    # Fallback : si les classes spécifiques évoluent, filtrer les conteneurs principaux
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

        # 1. Filtre par longueur et titres exclus (ex. menus de navigation)
        if not title or len(title) < 15 or title.lower() in EXCLUDED_TITLES:
            continue

        # 2. Filtre pour ne garder que les vrais liens d'articles
        if not ('/cms/c_' in href or '/news/' in href):
            continue

        full_url = urljoin(BASE_URL, href)

        # Dédoublonnage
        if full_url in seen_links:
            continue
        seen_links.add(full_url)

        # --- Extrait l'image de l'article ---
        image_url = None
        img_tag = block.find('img')
        if img_tag and img_tag.get('src'):
            src = img_tag.get('src') or img_tag.get('data-src')
            if src and not src.startswith('data:'): # Ignorer les images en base64
                image_url = urljoin(BASE_URL, src)

        # --- Extrait le résumé de l'article ---
        summary_text = title
        p_tag = block.find('p')
        if p_tag and len(p_tag.get_text(strip=True)) > 20:
            summary_text = p_tag.get_text(strip=True)

        # --- Construction de la description HTML avec l'image ---
        description_html = ""
        if image_url:
            description_html += f'<p><img src="{image_url}" alt="{title}" style="max-width:100%; height:auto;" /></p>'
        description_html += f'<p>{summary_text}</p>'

        # --- Ajout de l'entrée dans le flux ---
        fe = fg.add_entry()
        fe.id(full_url)
        fe.title(title)
        fe.link(href=full_url)
        fe.description(description_html)
        fe.pubDate(datetime.now(timezone.utc))

        # Attacher l'image en tant qu'enclosure RSS (compatible lecteurs RSS)
        if image_url:
            fe.enclosure(image_url, 0, 'image/jpeg')

        count += 1
        if count >= 30: # Limite aux 30 plus récents
            break

    fg.rss_file('feed.xml')
    print(f"Flux mis à jour : {count} articles valides avec images ajoutés.")

if __name__ == '__main__':
    build_rss()
