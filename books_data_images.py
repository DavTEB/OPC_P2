import os
import re
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# settings
START_URL   = "https://books.toscrape.com/catalogue/category/books_1/page-1.html"
OUTPUT_DIR  = "books_csv"
IMAGES_DIR  = "books_images"
MAX_PAGES   = 4        # None to scrape all pages
REQUEST_GAP = 0.5      # delay
TIMEOUT     = 20

# Session HTTP with one User-Agent 
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
})

def ensure_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)

def cleaner(s):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", (s or "")).strip("_") or "file"

def get_soup(url):
    r = SESSION.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")

def parse_listing_product_links(listing_url):
    soup = get_soup(listing_url)
    links = []
    for a in soup.select("article.product_pod h3 a"):
        href = a.get("href", "").strip()
        if href:
            links.append(urljoin(listing_url, href))
    return links

def get_next_page_url(listing_url):
    soup = get_soup(listing_url)
    nxt = soup.select_one("ul.pager li.next a")
    return urljoin(listing_url, nxt["href"]) if nxt and nxt.get("href") else None

def extract_book_data(product_url):
    soup = get_soup(product_url)

    title = (soup.select_one("div.product_main h1") or {}).get_text(strip=True)
    crumbs = [li.get_text(strip=True) for li in soup.select("ul.breadcrumb li")]
    category = crumbs[2] if len(crumbs) >= 4 else "Default"

    # Table specs
    specs = {}
    for tr in soup.select("table.table.table-striped tr"):
        th = tr.select_one("th")
        td = tr.select_one("td")
        if th and td:
            specs[th.get_text(strip=True)] = td.get_text(strip=True)

    upc = specs.get("UPC", "")
    price_incl = specs.get("Price (incl. tax)", "").replace("£", "").strip()
    price_excl = specs.get("Price (excl. tax)", "").replace("£", "").strip()
    availability = specs.get("Availability", "")

    # Description
    desc_p = soup.select_one("#product_description ~ p") or soup.select_one("#product_description + p")
    description = desc_p.get_text(strip=True) if desc_p else ""

    # Image URL (relative)
    img = soup.select_one("#product_gallery img")
    img_src = img["src"].strip() if img and img.has_attr("src") else ""
    image_url = urljoin(product_url, img_src) if img_src else ""

    return {
        "title": title,
        "upc": upc,
        "price_incl_tax_gbp": price_incl,
        "price_excl_tax_gbp": price_excl,
        "availability": availability,
        "description": description,
        "category": category,
        "product_page_url": product_url,
        "image_url": image_url,
    }

def download_image(image_url, category, upc, title, referer_url):
    if not image_url:
        return ""
    folder = os.path.join(IMAGES_DIR, cleaner(category))
    os.makedirs(folder, exist_ok=True)

    # simpler file name
    name = cleaner(upc or title or "image") + ".jpg"
    dest = os.path.join(folder, name)

    # Skip if present already and non-empty
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest

    try:
        headers = {"Referer": referer_url}
        with SESSION.get(image_url, headers=headers, timeout=TIMEOUT, stream=True) as r:
            r.raise_for_status()
            tmp = dest + ".part"
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)
            os.replace(tmp, dest)
        return dest
    except Exception:
        return ""

def scrape_all(start_url, max_pages=None):
    data_by_cat = {}
    page_url = start_url
    page_no = 1

    while page_url:
        print(f"Page {page_no}: {page_url}")
        links = parse_listing_product_links(page_url)
        print(f"  {len(links)} produits")

        for i, url in enumerate(links, 1):
            print(f"   - {i}/{len(links)} {url}")
            d = extract_book_data(url)
            # download now the image
            d["image_path"] = download_image(
                d["image_url"], d["category"], d["upc"], d["title"], url
            )
            cat = d.get("category") or "Default"
            data_by_cat.setdefault(cat, []).append(d)
            time.sleep(REQUEST_GAP)

        # clean stop after next page
        if max_pages is not None and page_no >= max_pages:
            print(f"Stop pagination: max_pages={max_pages}")
            break

        next_url = get_next_page_url(page_url)
        if next_url:
            page_url = next_url
            page_no += 1
        else:
            page_url = None

    return data_by_cat

def write_csvs(data_by_cat):
    cols = [
        "title","upc","price_incl_tax_gbp","price_excl_tax_gbp","availability",
        "description","category","product_page_url","image_url","image_path"
    ]
    total = 0
    for cat, rows in data_by_cat.items():
        df = pd.DataFrame(rows)
        # check columns
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        df = df[cols]
        out = os.path.join(OUTPUT_DIR, f"{cleaner(cat)}.csv")
        df.to_csv(out, index=False, encoding="utf-8")
        total += len(df)
        print(f"  CSV: {out} ({len(df)} lines)")
    print(f"Done: {total} books.")

if __name__ == "__main__":
    ensure_dirs()
    data = scrape_all(START_URL, max_pages=MAX_PAGES)
    if data:
        write_csvs(data)
    else:
        print("No book found.")
