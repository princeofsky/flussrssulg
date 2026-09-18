import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
from urllib.parse import urljoin

BASE_URL = "https://www.news.uliege.be/cms/c_9435330/fr/portail-news-agendas-toutes-les-news"

def build_rss():
    # 1. Télécharger la page web
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    response = requests.get(BASE_URL, headers=headers)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.content, "html.parser")

    # 2. Configurer le flux RSS
    fg = FeedGenerator()
    fg.id(BASE_URL)
    fg.title("ULiège - Toutes les news")
    fg.author({'name': 'Université de Liège'})
    fg.link(href=BASE_URL, rel='alternate')
    fg.description("Flux RSS non-officiel des actualités de l'Université de Liège")
    fg.language('fr')

    # 3. Extraire les articles (Ajuster les sélecteurs CSS selon la structure)
    # Sur l'agenda ULiège, les articles sont généralement contenus dans des balises 'article' ou des divs spécifiques
    articles = soup.find_all(['article', 'div'], class_=['news-item', 'item', 'c_9435330']) 
    
    # Si la structure utilise des liens simples dans une liste d'actualités :
    if not articles:
        articles = soup.select('.fiche-summary, .agenda-item, .content-list item')

    for art in articles:
        link_tag = art.find('a', href=True)
        if not link_tag:
            continue

        title = link_tag.get_text(strip=True)
        link = urljoin(BASE_URL, link_tag['href'])
        
        # Extrait la description si disponible
        desc_tag = art.find(['p', 'div'], class_=['chapeau', 'description', 'summary'])
        description = desc_tag.get_text(strip=True) if desc_tag else title

        # Ajouter l'élément au flux RSS
        fe = fg.add_entry()
        fe.id(link)
        fe.title(title)
        fe.link(href=link)
        fe.description(description)
        fe.pubDate(datetime.now(timezone.utc)) # Date de détection

    # 4. Sauvegarder le fichier XML
    fg.rss_file('feed.xml')

if __name__ == '__main__':
    build_rss()
