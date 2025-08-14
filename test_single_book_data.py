import warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.NotOpenSSLWarning)

import requests
from bs4 import BeautifulSoup
import pandas as pd

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
        'description': description
    }

# Test avec un livre
book_url = "https://books.toscrape.com/catalogue/soumission_998/index.html"
data = scrape_book(book_url)

# Afficher les résultats
print("=== DONNÉES DU LIVRE ===")
for key, value in data.items():
    print(f"{key}: {value}")


# Sauvegarder
df = pd.DataFrame([data])
df.to_csv('book_data.csv', index=False)
print("\nDonnées sauvées dans book_data.csv !")
