import os
import re
import time
import csv
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from os.path import basename, splitext

# =============== Settings ===============
START_URL = "https://books.toscrape.com/catalogue/category/books_1/page-1.html"
OUTPUT_DIR = "books_csv"
IMAGES_DIR = "books_images"
TIMEOUT = 20
REQUEST_DELAY = 0.5      # polite delay between product requests
MAX_PAGES = None            # None to scrape ALL pages, 2 for testing 
VERBOSE_IMAGES = True    # print each image download step

# One HTTP session for all requests
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
})


# =============== Helpers ===============
def cleaner(s):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", (s or "")).strip("_") or "file"


def ensure_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)


def get_soup(url):
    r = SESSION.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")


def parse_listing_product_links(listing_url):
    soup = get_soup(listing_url)
    links = []
    for a in soup.select("article.product_pod h3 a"):
        href = a.get("href", "").strip()
        if not href:
            continue
        links.append(urljoin(listing_url, href))
    return links


def get_next_page_url(current_url):
    soup = get_soup(current_url)
    nxt = soup.select_one("ul.pager li.next a")
    if not nxt:
        return None
    return urljoin(current_url, nxt.get("href", ""))


def extract_text(el):
    return el.get_text(strip=True) if el else ""


def extract_book_data(product_url):
    soup = get_soup(product_url)

    title = extract_text(soup.select_one("div.product_main h1"))

    # Breadcrumb: Home > Books > Category > Title
    crumbs = [extract_text(li) for li in soup.select("ul.breadcrumb li")]
    category = crumbs[2] if len(crumbs) >= 4 else "Default"

    # Table data
    data = {}
    for row in soup.select("table.table.table-striped tr"):
        key = extract_text(row.select_one("th"))
        val = extract_text(row.select_one("td"))
        data[key] = val

    upc = data.get("UPC", "")

    # Prices and availability
    price_incl = data.get("Price (incl. tax)", "")
    price_excl = data.get("Price (excl. tax)", "")
    availability = data.get("Availability", "")

    # Description
    # On BooksToScrape, #product_description is a heading; the first following <p> is the description.
    desc = ""
    desc_p = soup.select_one("#product_description ~ p") or soup.select_one("#product_description + p")
    if desc_p:
        desc = extract_text(desc_p)

    # Image URL (relative like ../../media/cache/..)
    img = soup.select_one("#product_gallery img")
    img_src = img.get("src", "").strip() if img else ""
    image_url = urljoin(product_url, img_src) if img_src else ""

    return {
        "title": title,
        "upc": upc,
        "price_incl_tax_gbp": price_incl.replace("£", "").strip(),
        "price_excl_tax_gbp": price_excl.replace("£", "").strip(),
        "availability": availability,
        "description": desc,
        "category": category,
        "product_page_url": product_url,
        "image_url": image_url
    }


def guess_ext_from_ct(content_type, default_ext=".jpg"):
    if not content_type:
        return default_ext
    ct = content_type.split(";")[0].strip().lower()
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
        "image/tiff": ".tif",
        "image/svg+xml": ".svg",
    }
    return mapping.get(ct, default_ext)


def save_image(image_url, category, upc, title, referer_url, images_log):
    """
    Download image and return local path; also append a record to images_log.
    """
    record = {
        "product_page_url": referer_url,
        "title": title,
        "upc": upc,
        "category": category,
        "image_url": image_url,
        "image_path": "",
        "downloaded": False,
        "http_status": "",
        "bytes": 0,
        "error": ""
    }

    if not image_url:
        images_log.append(record)
        return ""

    folder = os.path.join(IMAGES_DIR, cleaner(category or "Unknown"))
    os.makedirs(folder, exist_ok=True)

    # Try to keep original extension; if missing, we’ll refine after HEAD/GET
    url_path = image_url.split("?", 1)[0]
    ext = splitext(basename(url_path))[1].lower() or ".jpg"
    base_name = cleaner(upc or title or "image")
    dest_path = os.path.join(folder, base_name + ext)

    # Skip if already exists and non-empty
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        record.update({
            "image_path": dest_path,
            "downloaded": True,
            "http_status": "cached",
            "bytes": os.path.getsize(dest_path),
        })
        images_log.append(record)
        if VERBOSE_IMAGES:
            print(f"   [img] Cached: {dest_path}")
        return dest_path

    # Try with Referer
    headers = {"Referer": referer_url} if referer_url else {}

    try:
        with SESSION.get(image_url, timeout=TIMEOUT, headers=headers, stream=True) as r:
            record["http_status"] = str(r.status_code)
            r.raise_for_status()

            ctype = r.headers.get("Content-Type", "")
            if not ctype.lower().startswith("image/"):
                raise ValueError(f"Unexpected Content-Type: {ctype}")

            # If extension seems wrong, pick one from Content-Type
            guessed_ext = guess_ext_from_ct(ctype, default_ext=ext)
            if guessed_ext != ext:
                ext = guessed_ext
                dest_path = os.path.join(folder, base_name + ext)

            # Write stream to file
            tmp_path = dest_path + ".part"
            total = 0
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total += len(chunk)
            os.replace(tmp_path, dest_path)

            record.update({
                "image_path": dest_path,
                "downloaded": True,
                "bytes": total
            })
            if VERBOSE_IMAGES:
                print(f"   [img] Saved: {dest_path} ({total} bytes)")

    except Exception as e:
        record["error"] = str(e)
        if VERBOSE_IMAGES:
            print(f"   [img] FAIL: {image_url} -> {e}")

    images_log.append(record)
    return record["image_path"]


def scrape_all_books(start_url, delay=0.2, max_pages=None):
    """
    Crawl listing pages, scrape each product page, download images,
    return dict category -> list[rows], plus the images_log list.
    """
    by_category = {}
    images_log = []

    current_url = start_url
    page_number = 1

    while current_url:
        print(f"\n📄 Listing page {page_number}: {current_url}")
        try:
            product_links = parse_listing_product_links(current_url)
        except Exception as e:
            print(f"[!] Failed to parse listing {current_url}: {e}")
            break

        print(f"   Found {len(product_links)} products")
        for idx, book_url in enumerate(product_links, 1):
            print(f"   • {idx}/{len(product_links)} {book_url}")
            try:
                data = extract_book_data(book_url)
                # Download image now and set image_path
                img_path = save_image(
                    data.get("image_url"),
                    data.get("category"),
                    data.get("upc"),
                    data.get("title"),
                    referer_url=book_url,
                    images_log=images_log
                )
                data["image_path"] = img_path

                cat = data.get("category") or "Default"
                by_category.setdefault(cat, []).append(data)
            except Exception as e:
                print(f"       [!] Error scraping {book_url}: {e}")
            time.sleep(delay)

        # After finishing this page, decide pagination
        if max_pages is not None and page_number >= max_pages:
            print(f"Reached max_pages={max_pages}. Stop pagination.")
            break

        next_url = None
        try:
            next_url = get_next_page_url(current_url)
        except Exception as e:
            print(f"[!] Failed to resolve next page from {current_url}: {e}")

        if next_url:
            current_url = next_url
            page_number += 1
            print("➡️  Next page\n")
        else:
            print("✅ No more pages.\n")
            current_url = None

    return by_category, images_log


def write_category_csvs(by_category):
    wanted_cols = [
        "title", "upc",
        "price_incl_tax_gbp", "price_excl_tax_gbp", "availability",
        "description", "category", "product_page_url",
        "image_url", "image_path",
    ]

    total = 0
    categories_written = 0
    for category_name, rows in by_category.items():
        total += len(rows)
        safe_name = cleaner(category_name)
        out_path = os.path.join(OUTPUT_DIR, f"{safe_name}.csv")

        df = pd.DataFrame(rows)
        for c in wanted_cols:
            if c not in df.columns:
                df[c] = ""
        df = df[wanted_cols]
        df.to_csv(out_path, index=False, encoding="utf-8")
        categories_written += 1
        print(f"💾 Saved {len(rows)} rows to: {out_path}")

    return categories_written, total


def write_images_csv(images_log):
    out_path = os.path.join(OUTPUT_DIR, "images_downloads.csv")
    fieldnames = [
        "product_page_url", "title", "upc", "category",
        "image_url", "image_path", "downloaded", "http_status", "bytes", "error"
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in images_log:
            w.writerow(row)
    print(f"💾 Saved image log: {out_path} ({len(images_log)} rows)")


# Main to conclude what have been done 
if __name__ == "__main__":
    ensure_dirs()
    print("🔎 Scraping ALL books from master listing...\n")
    by_category, images_log = scrape_all_books(
        START_URL, delay=REQUEST_DELAY, max_pages=MAX_PAGES
    )

    if not by_category:
        print("[!] No data collected. Nothing to write.")
    else:
        cats, total = write_category_csvs(by_category)
        write_images_csv(images_log)
        print(f"\n🎉 Finished. Categories written: {cats} | Total books: {total}")
