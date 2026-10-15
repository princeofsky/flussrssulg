def build_rss():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.9,en;q=0.9"
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

    main_content = soup.find('main') or soup.find('div', id='content') or soup

    # Nettoyage des éléments indésirables
    for unwanted in main_content.find_all(['footer', 'nav', 'aside'], class_=re.compile(r'footer|menu|sidebar|navigation|bottom', re.I)):
        unwanted.decompose()

    # Élargissement maximal de la recherche de cartes ou blocs potentiels
    cards = main_content.select(
        '.k-card, .k-tile, article, .fiche-summary, .content-list-item, '
        '[class*="k-card"], [class*="card"], [class*="item"], [class*="news"]'
    )
    
    # Si toujours rien, on bascule en mode large : on prend tous les blocs <li> ou <div> contenant des liens vers /cms/
    if not cards:
        print("Aucune carte standard trouvée, passage en mode de secours élargi...")
        cards = main_content.find_all(['div', 'li', 'article'], href=False)

    print(f"Nombre de blocs bruts identifiés : {len(cards)}")

    seen_links = set()
    count = 0

    for card in cards:
        # Recherche de lien à l'intérieur du bloc
        link_tag = card.find('a', href=True) if hasattr(card, 'find') else None
        if not link_tag:
            continue

        href = link_tag.get('href')
        if not href or href.startswith('#') or href.startswith('javascript:'):
            continue

        full_url = clean_url(href)

        if not full_url or 'uliege.be' not in full_url:
            continue

        # Filtrer pour ne garder que les liens pointant vers des contenus de news/cms de l'ULiège
        if '/cms/' not in full_url and '/actualites/' not in full_url:
            continue

        # Extraction du titre (via le lien ou un titre interne)
        title_tag = card.find(['h1', 'h2', 'h3', 'h4', 'h5']) if hasattr(card, 'find') else None
        title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)

        if not title or len(title) < 10 or title.lower() in EXCLUDED_TITLES:
            continue

        if is_agenda_item(card, href, title):
            continue

        if full_url in seen_links:
            continue
        seen_links.add(full_url)

        # Extraction image et résumé
        image_url = extract_image(card, full_url) if hasattr(card, 'find') else None
        
        summary_text = ""
        p_tag = card.find('p') if hasattr(card, 'find') else None
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
            history[full_url] = pub_date.isoformat()

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
