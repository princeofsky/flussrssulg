# 1. cibler le conteneur principal de la page
    main_content = soup.find('main') or soup.find('div', id='content') or soup

    # 2. Récupérer TOUS les liens du contenu principal
    all_links = main_content.find_all('a', href=True)

    seen_links = set()
    count = 0

    for link_tag in all_links:
        href = link_tag['href']
        title = link_tag.get_text(strip=True)

        # Filtre sur le format d'URL d'un article ULiège (ex: /cms/c_20735269/...)
        if not ('/cms/c_' in href or '/news/' in href):
            continue

        # Exclure si le titre est trop court ou fait partie du menu
        if not title or len(title) < 15 or title.lower() in EXCLUDED_TITLES:
            continue

        full_url = urljoin(BASE_URL, href)

        # Dédoublonnage
        if full_url in seen_links:
            continue
        seen_links.add(full_url)

        # Trouver le bloc parent le plus proche pour récupérer l'image et le paragraphe d'extrait
        parent_block = link_tag.find_parent(['article', 'div', 'li']) or link_tag

        # Extrait de l'image
        image_url = None
        img_tag = parent_block.find('img')
        if img_tag:
            src = img_tag.get('src') or img_tag.get('data-src')
            if src and not src.startswith('data:'):
                image_url = urljoin(BASE_URL, src)

        # Extrait du résumé
        summary_text = title
        p_tag = parent_block.find('p')
        if p_tag and len(p_tag.get_text(strip=True)) > 20:
            summary_text = p_tag.get_text(strip=True)

        # Gestion de l'historique de date
        if full_url in history:
            pub_date = datetime.fromisoformat(history[full_url])
        else:
            pub_date = datetime.now(timezone.utc)
            history[full_url] = pub_date.isoformat()

        # Construction du flux RSS
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
