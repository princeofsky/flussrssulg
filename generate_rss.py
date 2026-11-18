import sys
import json
import os
import re

print("Étape 1 : Modules de base importés.")

from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
import urllib.request

print("Étape 2 : BeautifulSoup, FeedGenerator et urllib importés.")

BASE_URL = "https://www.news.uliege.be/cms/c_9435330/fr/portail-news-agendas-toutes-les-news"
DOMAIN_BASE = "https://www.news.uliege.be"

def fetch_page_html():
    print(f"Interrogation de {BASE_URL} via urllib...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    }
    req = urllib.request.Request(BASE_URL, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            html_content = response.read().decode('utf-8', errors='ignore')
            print(f"Statut HTTP : {response.status}")
            return html_content
    except Exception as e:
        print(f"Erreur lors de la requête HTTP : {e}")
        return ""

def run_diagnostic():
    html_content = fetch_page_html()
    print(f"Taille du HTML récupéré : {len(html_content)} octets")
    
    soup = BeautifulSoup(html_content, "html.parser")
    
    # 1. Analyser les balises script pour voir si des données JSON y sont cachées
    scripts = soup.find_all('script')
    print(f"DIAGNOSTIC : {len(scripts)} balises <script> trouvées sur la page.")
    
    for i, script in enumerate(scripts):
        content = script.string
        if content and len(content) > 100:
            if 'c_' in content or 'url' in content or 'title' in content or 'item' in content:
                print(f"  -> Script #{i} (taille: {len(content)} car.) contient des mots-clés pertinents.")
                print(f"     Extrait : {content[:150].strip()}...")

    # 2. Chercher toutes les occurrences de patterns JCMS de type c_suivi de chiffres dans le texte brut
    c_matches = re.findall(r'c_\d{6,8}', html_content)
    unique_c = list(set(c_matches))
    print(f"DIAGNOSTIC : {len(unique_c)} identifiants JCMS uniques (c_...) trouvés dans le texte brut.")
    if unique_c:
        print(f"  -> Exemples d'IDs trouvés : {unique_c[:15]}")

    # 3. Chercher si des attributs data-* contiennent des liens ou des titres
    elements_with_data = soup.find_all(lambda tag: any(attr.startswith('data-') for attr in tag.attrs))
    print(f"DIAGNOSTIC : {len(elements_with_data)} éléments HTML avec des attributs data-* trouvés.")

if __name__ == '__main__':
    try:
        print("Démarrage du diagnostic des 481 Ko...")
        run_diagnostic()
        print("Diagnostic terminé avec succès !")
    except Exception as e:
        import traceback
        print("ERREUR FATALE DU SCRIPT :")
        traceback.print_exc()
        sys.exit(1)
