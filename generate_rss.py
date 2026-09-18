import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
from urllib.parse import urljoin

BASE_URL = "https://www.news.uliege.be/cms/c_9435330/fr/portail-news-agendas-toutes-les-news"

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

    # Ciblage spécifique de la grille/liste d'articles ULiège
    articles = soup.find_all(['article', 'div'], class_=lambda c: c and ('news' in c or 'item' in c or 'card' in c or 'fiche' in c))
    
    # Si la recherche par classe échoue, on extrait les blocs contenant des liens vers /cms/c_
    if not articles:
        articles = soup.find_all('a', href=True)

    seen_links = set()
    count = 0

    for item in articles:
        # Extraire la balise <a> si item est une div/article, sinon utiliser item directement
        link_tag = item if item.name == 'a' else item.find('a', href=True)
        
        if not link_tag or not link_tag.get('href'):
            continue

        href = link_tag['href']
        title = link_tag.get_text(strip=True)

        # Filtre les liens internes pertinents vers les actualités (exclut le menu, l'en-tête, etc.)
        if title and len(title) > 12 and ('/cms/c_' in href or '/news/' in href):
            full_url = urljoin(BASE_URL, href)

            # Évite les doublons dans le flux
            if full_url in seen_links:
                continue
            seen_links.add(full_url)

            # Extrait un résumé s'il existe
            summary = title
            parent = link_tag.find_parent(['div', 'article', 'li'])
            if parent:
                p_tag = parent.find('p')
                if p_tag and len(p_tag.get_text(strip=True)) > 20:
                    summary = p_tag.get_text(strip=True)

            fe = fg.add_entry()
            fe.id(full_url)
            fe.title(title)
            fe.link(href=full_url)
            fe.description(summary)
            fe.pubDate(datetime.now(timezone.utc))
            
            count += 1
            if count >= 30: # Limite aux 30 plus récents
                break

    fg.rss_file('feed.xml')
    print(f"Flux généré avec succès : {count} articles trouvés.")

if __name__ == '__main__':
    build_rss()
