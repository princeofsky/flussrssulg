def build_rss():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    
    print(f"Interrogation de {BASE_URL}...")
    response = requests.get(BASE_URL, headers=headers, timeout=15)
    print(f"Code HTTP reçu : {response.status_code}")
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

    # On cible directement TOUS les liens de la page contenant '/cms/' (la structure des articles ULiège)
    all_links = soup.find_all('a', href=True)
    print(f"Nombre total de liens trouvés sur la page : {len(all_links)}")

    seen_links = set()
    count = 0

    for link in all_links:
        href = link.get('href')
        if not href or href.startswith('#') or href.startswith('javascript:'):
            continue

        full_url = clean_url(href)

        # On ne garde que les liens internes pointant vers le système de CMS de news de l'ULiège
        if not full_url or 'uliege.be' not in full_url or '/cms/' not in full_url:
            continue

        # Récupération du texte du lien ou d'un titre proche
        title = link.get_text(strip=True)
        
        # Si le lien lui-même n'a pas de texte, on cherche un titre (h1-h5) dans le parent direct
        if not title or len(title) < 10:
            parent = link.find_parent(['article', 'div', 'li', 'p'])
            if parent:
                t_tag = parent.find(['h1', 'h2', 'h3', 'h4', 'h5'])
                if t_tag:
                    title = t_tag.get_text(strip=True)

        # Application de vos filtres de titre
        if not title or len(title) < 10 or title.lower() in EXCLUDED_TITLES:
            continue

        # Vérification agenda
        parent_container = link.find_parent(['article', 'div', 'li']) or link
        if is_agenda_item(parent_container, href, title):
            continue

        # Dédoublonnage strict par URL
        if full_url in seen_links:
            continue
        seen_links.add(full_url)

        # Recherche d'image dans le conteneur parent le plus proche
        image_url = extract_image(parent_container, full_url)

        # Extraction d'un résumé potentiel (<p> dans le parent)
        summary_text = ""
        p_tag = parent_container.find('p')
        if p_tag:
            p_text = p_tag.get_text(strip=True)
            if len(p_text) > 15 and p_text.lower() != title.lower():
                summary_text = p_text

        if not summary_text:
            summary_text = title

        # Gestion de l'historique des dates
        if full_url in history:
            pub_date = datetime.fromisoformat(history[full_url])
        else:
            pub_date = datetime.now(timezone.utc)
            history[full_url] = pub_date.isoformat()

        # Construction du HTML
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
    try:
        build_rss()
    except Exception as e:
        print(f"ERREUR CRITIQUE DANS LE SCRIPT : {e}")
        raise e

all_links = soup.find_all('a', href=True)
    print(f"DEBUG TOTAL : {len(all_links)} liens trouvés sur la page.")
    
    for link in all_links[:15]:  # Afficher les 15 premiers liens pour diagnostic
        print(f"Lien brut : {link.get('href')} -> Texte : {link.get_text(strip=True)[:30]}")
