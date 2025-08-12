import os
import re
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# --------- Settings ---------
# This "Books" super-category lists ALL books across many pages
START_URL = "https://books.toscrape.com/catalogue/category/books_1/page-1.html"
OUTPUT_DIR = "books_csv"
IMAGES_DIR = "books_images"
TIMEOUT = 20           # network timeout (seconds)
REQUEST_DELAY = 0.5    # polite delay between product requests
MAX_PAGES = 2          # set to None to scrape ALL pages (will take longer)

# HTTP session with a basic User-Agent (helps avoid occasional blocks)
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
})


# --------- Small helpers ---------
def sanitize(s):
    """Make a safe filename: keep letters/numbers/_/- only."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s or "").strip("_") or "file"


def save_image(image_url, category, upc, title, referer_url=None):
    """
    Download the product image (if not already present) and return local path.
    Folder: IMAGES_DIR/<Category>/
    Filename: <UPC>.<ext> (fallback: <Title>.<ext>)
    """
    if not image_url:
        return ""

    folder = os.path.join(IMAGES_DIR, sanitize(category or "Unknown"))
    os.makedirs(folder, exist_ok=True)

    # Try to keep original extension; default to .jpg if unknown
    from os.path import basename, splitext
    url_path = image_url.split("?", 1)[0]
    ext = splitext(basename(url_path))[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        ext = ".jpg"

    base_name = sanitize(upc or title or "image")
    dest_path = os.path.join(folder, base_name + ext)

    if os.path.exists(dest_path):
        return dest_path

    # First attempt
    try:
        with SESSION.get(image_url, timeout=TIMEOUT, stream=True) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
        return dest_path
    except requests.HTTPError:
        # Retry with Referer if needed
        headers = {}
        if referer_url:
            headers["Referer"] = referer_url
        with SESSION.get(image_url, timeout=TIMEOUT, stream=True, headers=headers) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
        return dest_path


# --------- Scrape a single product page ---------
def scrape_book(url):
    """Scrape one product page and return a dict of fields (incl. image)."""
    r = SESSION.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "lxml")

    # Title
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else "N/A"

    # Product info table
    upc = ""
    price_incl_tax = ""
    price_excl_tax = ""
    availability = ""
    table = soup.find("table", class_="table table-striped")
    if table:
        for row in table.find_all("tr"):
            th, td = row.find("th"), row.find("td")
            if not th or not td:
                continue
            key = th.get_text(strip=True)
            val = td.get_text(strip=True)
            if key == "UPC":
                upc = val
            elif key == "Price (incl. tax)":
                price_incl_tax = val.replace("£", "")
            elif key == "Price (excl. tax)":
                price_excl_tax = val.replace("£", "")
            elif key == "Availability":
                m = re.search(r"(\d+)", val)
                availability = m.group(1) if m else "0"

    # Description
    description = ""
    anchor = soup.find("div", id="product_description")
    if anchor:
        p = anchor.find_next_sibling("p")
        if p:
            description = p.get_text(strip=True)

    # Category (breadcrumb: Home > Books > Category > Book)
    category = "Unknown"
    bc_links = soup.select("ul.breadcrumb li a")
    if len(bc_links) >= 3:
        # The last <a> before the active item is the category (e.g., Poetry)
        category = bc_links[-1].get_text(strip=True)

    # Image URL (absolute) + download
    image_url = ""
    image_path = ""
    img_tag = soup.select_one("#product_gallery img")
    if img_tag and img_tag.get("src"):
        image_url = urljoin(url, img_tag["src"])  # ../../media/... -> absolute
        try:
            image_path = save_image(image_url, category, upc, title, referer_url=url)
        except Exception:
            # Keep URL even if download fails
            image_path = ""

    return {
        "title": title,
        "upc": upc,
        "price_incl_tax_gbp": price_incl_tax,
        "price_excl_tax_gbp": price_excl_tax,
        "availability": availability,
        "description": description,
        "category": category,
        "product_page_url": url,
        "image_url": image_url,
        "image_path": image_path,
    }


# --------- Listing helpers ---------
def get_book_urls_from_page(list_url):
    """Return absolute product URLs found on one listing page."""
    r = SESSION.get(list_url, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "lxml")

    urls = []
    for a in soup.select("article.product_pod h3 a"):
        href = a.get("href")
        if href:
            urls.append(urljoin(list_url, href))
    return urls


def get_next_page_url(current_url):
    """Return absolute URL of the next listing page, or None if none."""
    r = SESSION.get(current_url, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "lxml")

    nxt = soup.select_one("li.next a")
    if nxt and nxt.get("href"):
        return urljoin(current_url, nxt["href"])
    return None


# --------- Iterate over all listing pages ---------
def scrape_all_books(start_url, delay=0.5, max_pages=None):
    """
    Go through listing pages, scrape each product, and group results by category.
    Returns a dict: {category_name: [rows]}.
    """
    by_category = {}
    current_url = start_url
    page_number = 1

    while current_url:
        print(f"Page {page_number}: {current_url}")

        # Collect product links on this page
        try:
            book_urls = get_book_urls_from_page(current_url)
        except Exception as e:
            print(f"[!] Failed to read listing page: {e}")
            book_urls = []

        print(f"   → Found {len(book_urls)} books")

        # Visit each product page
        for i, book_url in enumerate(book_urls, 1):
            print(f"     • {i}/{len(book_urls)} {book_url}")
            try:
                data = scrape_book(book_url)
                cat = data.get("category") or "Unknown"
                by_category.setdefault(cat, []).append(data)
            except Exception as e:
                print(f"       [!] Error scraping {book_url}: {e}")
            time.sleep(delay)  # be polite

        # Stop pagination AFTER finishing this page
        if max_pages is not None and page_number >= max_pages:
            print(f"Reached max_pages={max_pages}. Stop pagination.")
            current_url = None
            break  # leaving the loop; function will return collected data

        # Else move to next page
        next_url = None
        try:
            next_url = get_next_page_url(current_url)
        except Exception as e:
            print(f"[!] Failed to resolve next page: {e}")

        if next_url:
            current_url = next_url
            page_number += 1
            print("➡️  Next page\n")
        else:
            print("✅ No more pages.\n")
            current_url = None

    return by_category


# --------- Execution ---------
if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)

    print("🔎 Scraping ALL books via the master listing ...\n")
    grouped = scrape_all_books(START_URL, delay=REQUEST_DELAY, max_pages=MAX_PAGES)

    # Ensure a stable set/order of columns in CSVs
    wanted_cols = [
        "title", "upc",
        "price_incl_tax_gbp", "price_excl_tax_gbp", "availability",
        "description", "category", "product_page_url",
        "image_url", "image_path",
    ]

    # Write one CSV per category (even if some are empty)
    total = 0
    categories_written = 0

    if not grouped:
        print("[!] No data collected. Nothing to write.")
    else:
        for category_name, rows in grouped.items():
            total += len(rows)
            safe_name = sanitize(category_name)
            out_path = os.path.join(OUTPUT_DIR, f"{safe_name}.csv")

            df = pd.DataFrame(rows)
            for c in wanted_cols:
                if c not in df.columns:
                    df[c] = ""
            df = df[wanted_cols]
            df.to_csv(out_path, index=False, encoding="utf-8")
            categories_written += 1
            print(f"💾 Saved {len(rows)} rows to: {out_path}")

    print(f"\n🎉 Finished. Categories written: {categories_written} | Total books: {total}")

