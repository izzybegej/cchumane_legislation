# run_scraper.py
# --------------
# This script is called by the GitHub Action (scrape.yml).
# It runs the scraper and saves the output as docs/bills.json
# so the website widget can read it at a public URL.
#
# Kept separate from scraper.py so the YAML workflow file
# doesn't have to embed Python code (which causes syntax conflicts).

import json
import os
from scraper import scrape_all_bills

print("Starting scheduled scrape...")
results = scrape_all_bills()

# Create the docs/ folder if it doesn't exist yet
# GitHub Pages serves files from this folder publicly
os.makedirs("docs", exist_ok=True)

with open("docs/bills.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"Saved {len(results)} bills to docs/bills.json")
