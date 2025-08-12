import warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.NotOpenSSLWarning)

import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin
import time

def scrape_book(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'lxml')
    
    # 1. Titre (facile à voir)
    title = soup.find('h1').text
    
    # 2. TOUT depuis le tableau - Simple et logique !
    table = soup.find('table', class_='table table-striped')
    
    # Variables pour stocker les données
    upc = ""
    price_incl_tax = ""
    price_excl_tax = ""
    availability = ""
    
    # On parcourt chaque ligne du tableau
    for row in table.find_all('tr'):
        cells = row.find_all(['th', 'td'])
        if len(cells) >= 2:
            key = cells[0].text.strip()
            value = cells[1].text.strip()
            
            if key == 'UPC':
                upc = value
            elif key == 'Price (incl. tax)':
                price_incl_tax = value.replace('£', '')
            elif key == 'Price (excl. tax)':
                price_excl_tax = value.replace('£', '')
            elif key == 'Availability':
                # Extraire juste le nombre
                if '(' in value:
                    availability = value.split('(')[1].split(' ')[0]
                else:
                    availability = "0"
    
    # 3. Description (juste en dessous)
    description_div = soup.find('div', id='product_description')
    if description_div:
        description = description_div.find_next_sibling('p').text
    else:
        description = "Pas de description"
    
    # Retourner les données
    return {
        'title': title,
        'upc': upc,
        'price_with_tax': price_incl_tax,
        'price_without_tax': price_excl_tax,
        'availability': availability,
        'description': description,
        'product_url': url  # Ajout de l'URL pour traçabilité
    }

def get_book_urls_from_page(category_url):
    """Extrait toutes les URLs de livres d'une page de catégorie"""
    response = requests.get(category_url)
    soup = BeautifulSoup(response.content, 'lxml')
    
    book_urls = []
    
    # Trouver tous les livres
    books = soup.find_all('article', class_='product_pod')
    
    for book in books:
        # Le lien est dans le h3 > a
        link_element = book.find('h3').find('a')
        if link_element:
            relative_url = link_element['href']
            full_url = urljoin(category_url, relative_url)
            book_urls.append(full_url)
    
    return book_urls

def get_next_page_url(current_url):
    """Vérifie s'il y a une page suivante"""
    response = requests.get(current_url)
    soup = BeautifulSoup(response.content, 'lxml')
    
    # Chercher le bouton "next"
    next_link = soup.find('li', class_='next')
    if next_link:
        next_url = next_link.find('a')['href']
        return urljoin(current_url, next_url)
    
    return None

def scrape_category(category_url):
    """Scrape tous les livres d'une catégorie avec pagination"""
    all_books_data = []
    current_url = category_url
    page_number = 1
    
    while current_url:
        print(f"📖 Scraping page {page_number}...")
        
        # Récupérer les URLs des livres de cette page
        book_urls = get_book_urls_from_page(current_url)
        print(f"Trouvés {len(book_urls)} livres sur cette page")
        
        # Scraper chaque livre
        for i, book_url in enumerate(book_urls, 1):
            print(f"  📚 Livre {i}/{len(book_urls)}")
            book_data = scrape_book(book_url)
            all_books_data.append(book_data)
            time.sleep(0.5)  # Pause pour être poli
        
        # Chercher la page suivante
        current_url = get_next_page_url(current_url)
        page_number += 1
        
        if current_url:
            print(f"➡️  Page suivante trouvée\n")
        else:
            print("✅ Terminé ! Aucune page suivante.\n")
    
    return all_books_data

# === EXECUTION ===

# URL category (exemple: Mystery)
category_url = "https://books.toscrape.com/catalogue/category/books/historical-fiction_4/index.html"

# Scraper toute la catégorie
books_data = scrape_category(category_url)

print(f"RESULTS: {len(books_data)} scraped books in a category")

if books_data:
    
    # Sauvegarde
    df = pd.DataFrame(books_data)
    df.to_csv('category_books.csv', index=False)
    
    print(f"\nDonnées sauvées dans: category_books.csv")
    print(f"Colonnes: {list(df.columns)}")

print("\n Terminé!")
