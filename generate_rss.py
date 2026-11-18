def build_rss():
    html_content = fetch_page_html()
    print(f"Taille du HTML récupéré via Playwright : {len(html_content)} octets")
    
    soup = BeautifulSoup(html_content, "html.parser")
    history = load_history()

    fg = FeedGenerator()
    fg.id(BASE_URL)
    fg.title("ULiège - Toutes les news")
    fg.author({'name': 'Université de Liège'})
    fg.link(href=BASE_URL, rel='alternate')
    fg.description("Flux RSS des actualités de l'Université de Liège")
    fg.language('fr')

    # Approche robuste : On cible tous les liens vers des articles (/cms/) sur la page,
    # en s'affranchissant des classes CSS des conteneurs qui changent tout le temps.
    all_links = soup.find_all('a', href=True)
    print(f"DEBUG : {len(all_links)} liens totaux trouvés sur la page.")

    seen_links = set()
    count = 0

    for link in all_links:
        href = link.get('href')
        full_url = clean_url(href)

        # Filtrer uniquement les liens valides d'articles ULiège contenant /cms/
        if not full_url or 'uliege.be' not in full_url or '/cms/' not in full_url:
            continue

        if any(exc in full_url.lower() for exc in EXCLUDED_URL_PARTS):
            continue

        # Sécurité anti-menus : Ignorer si le lien se trouve dans un menu, header ou footer
        if link.find_parent(['nav', 'header', 'footer', 'aside']):
            continue

        # Remonter au conteneur parent proche (ex: bloc de carte, li, div) pour trouver l'image
        container = link.find_parent(['article', 'div', 'li', 'section']) or link

        # Ignorer si le conteneur ou ses parents ont des classes de navigation/menu
        parent_classes = " ".join([str(cls) for p in link.parents for cls in p.get('class', [])]).lower()
        if any(term in parent_classes for term in ['menu', 'nav', 'breadcrumb', 'footer', 'header', 'facette', 'filter']):
            continue

        # Extraction du titre
        title = link.get_text(strip=True)
        if not title or len(title) < 15:
            title_tag = container.find(['h1', 'h2', 'h3', 'h4', 'h5'])
            if title_tag:
                title = title_tag.get_text(strip=True)

        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if any(exc in title_lower for exc in EXCLUDED_EXACT_TITLES):
            continue

        if is_agenda_item(container, href, title):
            continue

        if full_url in seen_links:
            continue
        seen_links.add(full_url)

        image_url = extract_image(container, full_url)
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

        count += 1
        if count >= 35:
            break

    save_history(history)
    fg.rss_file('feed.xml')
    print(f"Flux mis à jour : {count} articles valides enregistrés.")
