# Books to Scrape - Web Scraping - Openclassrooms Python Project 2 / 13
A web scraping project that extracts book information from the "Books to Scrape" website for educational purposes

## Project Overview

This project is part of my OpenClassrooms Python Developer path. It demonstrates web scraping techniques using Python to extract book data from http://books.toscrape.com.

## Features

- Single Book Scraping: Extract detailed information from individual book pages
- Category Scraping: Extract all books from specific categories
- Full Site Scraping: Extract all books from the entire website
- Image Download: Download and save book cover images
- CSV Export: Save extracted data in CSV format

## Technos used

- Python 3.9
- Requests: HTTP library for web requests
- Warnings: handling OpenSSL terminal warnings, not necessary if you have the right version of urllib3
- BeautifulSoup4: HTML parsing and data extraction
- lxml: Fast XML and HTML parser, performs better than html.parser
- Pandas: Data manipulation and CSV export
- urllib3: URL handling utilities
- time
- os

## Installation
Clone the repository
 ```bash
  git clone https://github.com/DavTEB/OPC_P2.git
        cd books_to_scrape
 ```

## Environnement virtuel (Python 3.9)

  Prérequis
  - Avoir Python 3.9 installé.
  - Vérifier:
    - macOS/Linux: `python3.9 --version`
    - Windows: `py -3.9 --version`

Création et activation du venv
- macOS / Linux
```bash
# À la racine du projet
python3.9 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

- Windows (PowerShell)
```powershell
# À la racine du projet
py -3.9 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Installer les dépendances
```bash
# Si requirements.txt existe
pip install -r requirements.txt
```

Désactiver l’environnement
```bash
deactivate
```
## Author 
David TEBELE
