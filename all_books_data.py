import warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.NotOpenSSLWarning)

import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin
import time
import os

# Start from the "Books" super-category that lists ALL books
START_URL = "https://books.toscrape.com/catalogue/category/books_1/page-1.html"
OUTPUT_DIR = "books_csv"

def scrape_book(url):
    """Scrape a single product page and return a dict of fields."""
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'lxml')
    
    # 1) Title (easy to see)
    h1 = soup.find('h1')
    title = h1.text if h1 else "N/A"
    
    # 2) All fields from the product information table
    table = soup.find('table', class_='table table-striped')
    
    upc = ""
    price_incl_tax = ""
    price_excl_tax = ""
    availability = ""
    
    if table:
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
                    # Extract just the number in stock
                    if '(' in value:
                        availability = value.split('(')[1].split(' ')[0]
                    else:
                        availability = "0"
    
    # 3) Description (just below the product description header)
    description_div = soup.find('div', id='product_description')
    if description_div:
        next_p = description_div.find_next_sibling('p')
        description = next_p.text if next_p else "Pas de description"
    else:
        description = "Pas de description"

    # 4) Category (from breadcrumb: Home > Books > Category > Book)
    category = "Unknown"
    # The anchors in breadcrumb usually are: Home, Books, Category
    bc_links = soup.select('ul.breadcrumb li a')
    if len(bc_links) >= 3:
        category = bc_links[-1].get_text(strip=True)

    return {
        'title': title,
        'upc': upc,
        'price_with_tax': price_incl_tax,
        'price_without_tax': price_excl_tax,
        'availability': availability,
        'description': description,
        'category': category,     # keep the category for grouping into CSVs
        'product_url': url
    }

def get_book_urls_from_page(list_url):
    """Extract all product URLs from a listing page (any category page)."""
    response = requests.get(list_url)
    soup = BeautifulSoup(response.content, 'lxml')
    
    book_urls = []
    books = soup.find_all('article', class_='product_pod')
    
    for book in books:
        link_element = book.find('h3').find('a')
        if link_element and link_element.get('href'):
            relative_url = link_element['href']
            full_url = urljoin(list_url, relative_url)
            book_urls.append(full_url)
    
    return book_urls

def get_next_page_url(current_url):
    """Return the absolute URL of the next page if it exists; otherwise None."""
    response = requests.get(current_url)
    soup = BeautifulSoup(response.content, 'lxml')
    
    next_link = soup.find('li', class_='next')
    if next_link and next_link.find('a'):
        next_url = next_link.find('a')['href']
        return urljoin(current_url, next_url)
    return None

def scrape_all_books(start_url, delay=0.5, max_pages=None):
    """
    Iterate over ALL pages of the 'Books' super-category, scrape each product,
    and group results by their real category name.
    """
    by_category = {}   # dict: {category_name: [rows]}
    current_url = start_url
    page_number = 1
    
    while current_url:
        if max_pages is not None and page_number > max_pages:
            print(f"Stopping after {max_pages} pages (global listing).")
            break
        else:
            print(f"📄 Scraping listing page {page_number}: {current_url}")
        
        # Collect product links on this page
        book_urls = get_book_urls_from_page(current_url)
        print(f"   → Found {len(book_urls)} books on this page")
        
        # Visit each product page
        for i, book_url in enumerate(book_urls, 1):
            print(f"     • Book {i}/{len(book_urls)}")
            try:
                data = scrape_book(book_url)
                cat = data.get('category', 'Unknown') or 'Unknown'
                by_category.setdefault(cat, []).append(data)
            except Exception as e:
                # Log the error and continue with the next book
                print(f"       [!] Error scraping {book_url}: {e}")
            time.sleep(delay)  # polite delay
        
        # Pagination
        next_url = get_next_page_url(current_url)
        current_url = next_url
        page_number += 1
        
        if current_url:
            print("➡️  Next page detected\n")
        else:
            print("✅ Done! No more pages.\n")
    
    return by_category

# === EXECUTION ===
if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("🔎 Scraping ALL books via the master listing ...\n")
    grouped = scrape_all_books(START_URL, delay=0.5, max_pages=2)

    total = 0
    for category_name, rows in grouped.items():
        total += len(rows)
        # Build a simple safe filename from the category name
        safe_name = category_name.replace("/", "-").replace("\\", "-").strip() or "Unknown"
        out_path = os.path.join(OUTPUT_DIR, f"{safe_name}.csv")
        df = pd.DataFrame(rows)
        df.to_csv(out_path, index=False)
        print(f"💾 Saved {len(rows)} rows to: {out_path}")

    print(f"\n🎉 Finished. Total books scraped across all categories: {total}")
