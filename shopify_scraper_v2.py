#!/usr/bin/env python3
"""
Shopify App Store Competitor Scraper v2
Extracts app metadata and reviews for fraud/bot prevention apps.
Uses curl for metadata and browser for reviews.
"""
import subprocess
import json
import re
import csv
import time
import os

def curl_fetch(url, ua=None):
    """Fetch a URL using curl."""
    cmd = ['curl', '-s', '-L', '--max-time', '30',
           '-A', ua or 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
           '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
           '-H', 'Accept-Language: en-US,en;q=0.9',
           url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def extract_json_ld_all(html):
    """Extract ALL JSON-LD blocks from HTML."""
    results = []
    for match in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL):
        try:
            data = json.loads(match.group(1))
            results.append(data)
        except json.JSONDecodeError:
            continue
    return results

def parse_app_data(html, name):
    """Parse app data from HTML."""
    data = {'name': name, 'status': 'ok'}
    
    # Extract title
    title_match = re.search(r'<title>([^<]+)</title>', html)
    data['title'] = title_match.group(1) if title_match else ''
    
    # Extract all JSON-LD
    ld_blocks = extract_json_ld_all(html)
    
    # Find SoftwareApplication in JSON-LD
    for ld in ld_blocks:
        if isinstance(ld, dict):
            if ld.get('@type') == 'SoftwareApplication':
                data['rating'] = ld.get('aggregateRating', {}).get('ratingValue', '')
                data['review_count'] = ld.get('aggregateRating', {}).get('ratingCount', '')
                data['category'] = ld.get('applicationCategory', '')
                data['brand'] = ld.get('brand', '')
                data['description'] = ld.get('description', '')
            if ld.get('@type') == 'Organization' or ld.get('@type') == 'Person':
                data['developer'] = ld.get('name', '')
            if 'aggregateRating' in ld and isinstance(ld['aggregateRating'], dict):
                data['rating'] = data.get('rating') or ld['aggregateRating'].get('ratingValue', '')
                data['review_count'] = data.get('review_count') or ld['aggregateRating'].get('ratingCount', '')
        elif isinstance(ld, list):
            for item in ld:
                if isinstance(item, dict) and item.get('@type') == 'SoftwareApplication':
                    data['rating'] = data.get('rating') or item.get('aggregateRating', {}).get('ratingValue', '')
                    data['review_count'] = data.get('review_count') or item.get('aggregateRating', {}).get('ratingCount', '')
                    data['brand'] = data.get('brand') or item.get('brand', '')
    
    # Extract description from meta
    desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
    if desc_match and not data.get('description'):
        data['description'] = desc_match.group(1)
    
    # Extract developer from page text
    dev_patterns = [
        r'by\s+([A-Za-z0-9\s\.&\-]+?)\s+(?:helps|protect|blocks|blocks|prevents|offers)',
        r'Developer</[^>]*>\s*<[^>]*>\s*([^<]+?)\s*<',
        r'<a[^>]*>Blockify</a>',
    ]
    for pat in dev_patterns:
        m = re.search(pat, html)
        if m and not data.get('developer'):
            data['developer'] = m.group(1).strip()
    
    # Use brand as developer fallback
    if not data.get('developer') and data.get('brand'):
        data['developer'] = data['brand']
    
    # Extract pricing - look for more patterns
    pricing_text = []
    # Pattern 1: $XX.XX/month or $XX.XX/year
    for m in re.finditer(r'\$([\d.]+)/\s*(month|year)', html):
        pricing_text.append(f"${m.group(1)}/{m.group(2)}")
    # Pattern 2: Free to install / Free plan / Free trial
    for m in re.finditer(r'(Free\s*(?:to\s*install|plan|trial))', html, re.IGNORECASE):
        pricing_text.append(m.group(1).strip())
    # Pattern 3: Look in pricing section headers
    for m in re.finditer(r'<h[1-6][^>]*>([^<]*(?:Free|\$)[^<]*)</h[1-6]>', html):
        pricing_text.append(m.group(1).strip())
    
    data['pricing'] = list(set(pricing_text))[:5]
    
    # Extract features from list items
    features = []
    list_items = re.findall(r'<li[^>]*>(.*?)</li>', html, re.DOTALL)
    skip_keywords = [
        'Sales channels', 'Finding products', 'Selling products',
        'Orders and shipping', 'Store design', 'Marketing and conversion',
        'Store management', 'Browse apps', 'Log in', 'Start for free',
        'App categories', 'Top categories', 'Dropshipping', 'Marketplaces',
        'Product reviews', 'Email marketing', 'SEO', 'Shipping',
        'Currency and translation', 'Shopify Help Center',
        'API documentation', 'Shopify Community', 'Community Events',
        'Shopify Blog', 'Research', 'About', 'Careers', 'Investors',
        'Developer login', 'Terms of service', 'Privacy policy',
        'California Consumer Privacy Act', 'Change your language',
        'appstore-side-navbar', 'appstore-side-search',
    ]
    
    for item in list_items:
        text = re.sub(r'<[^>]+>', '', item).strip()
        text = re.sub(r'\s+', ' ', text)
        if len(text) > 15 and len(text) < 400:
            if not any(kw in text for kw in skip_keywords):
                features.append(text)
    
    data['features'] = features[:15]
    
    # Extract release/update dates from JSON-LD
    for ld in ld_blocks:
        if isinstance(ld, dict):
            if ld.get('datePublished'):
                data['launch_date'] = ld['datePublished'][:10]
            if ld.get('dateModified'):
                data['last_update'] = ld['dateModified'][:10]
    
    return data

# Target apps
APP_TARGETS = [
    {"name": "Blockify Fraud Filter, Blocker", "url": "https://apps.shopify.com/blockify", "search": "blockify+fraud"},
    {"name": "Blocky Fraud Filter IP Blocker", "url": "https://apps.shopify.com/blocky-fraud-filter-ip-blocker", "search": "blocky+fraud"},
    {"name": "MIDA Fraud Filter, Bot Blocker", "url": "https://apps.shopify.com/mida-fraud-filter-bot-blocker", "search": "mida+fraud"},
    {"name": "Kedra Fraud Filter, IP Blocker", "url": "https://apps.shopify.com/kedra-fraud-filter-ip-blocker", "search": "kedra+fraud"},
    {"name": "NoFraud (Wyllo)", "url": "https://apps.shopify.com/nofraud-chargeback-prevention-and-protection", "search": "nofraud+wyllo"},
    {"name": "NoSpy - Anti Fraud Spy Blocker", "url": "https://apps.shopify.com/nospy-anti-fraud-spy-blocker", "search": "nospy+anti"},
    {"name": "Securify Bot & Country Blocker", "url": "https://apps.shopify.com/securify", "search": "securify+bot+country"},
    {"name": "Evereye | Fraud Protection", "url": "https://apps.shopify.com/evereye-fraud-protection", "search": "evereye+fraud"},
    {"name": "FraudBlock Fraud Prevention", "url": "https://apps.shopify.com/fraudblock-fraud-prevention", "search": "fraudblock"},
    {"name": "Fraud Judge Fraud Prevention", "url": "https://apps.shopify.com/fraud-judge-fraud-prevention", "search": "fraud+judge"},
    {"name": "Fraud Control", "url": "https://apps.shopify.com/fraud-control", "search": "fraud+control"},
    {"name": "Beacon Fraud Prevention", "url": "https://apps.shopify.com/beacon-fraud-prevention", "search": "beacon+fraud"},
    {"name": "FraudLabs Pro Fraud Prevention", "url": "https://apps.shopify.com/fraudlabs-pro-fraud-prevention", "search": "fraudlabs+fraud"},
    {"name": "X Shield: Fraud & Spy Blocker", "url": "https://apps.shopify.com/x-shield-fraud-spy-blocker", "search": "x+shield+fraud"},
    {"name": "Fraud Falcon - Fraud Filter", "url": "https://apps.shopify.com/fraud-falcon-fraud-filter", "search": "fraud+falcon"},
    {"name": "VOL Fraud Filter & Bot Blocker", "url": "https://apps.shopify.com/vol-fraud-filter-bot-blocker", "search": "vol+fraud"},
]

def main():
    print("=" * 60)
    print("Shopify App Store Competitor Scraper v2")
    print("=" * 60)
    
    # Fetch all app HTMLs
    print("\nFetching app pages...")
    for i, app in enumerate(APP_TARGETS):
        print(f"  [{i+1}/{len(APP_TARGETS)}] {app['name']}")
        app['html'] = curl_fetch(app['url'])
        time.sleep(0.3)
    
    # Parse all app data
    print("\nParsing data...")
    for app in APP_TARGETS:
        data = parse_app_data(app['html'], app['name'])
        app.update(data)
        status = app.get('status', 'unknown')
        rating = app.get('rating', '?')
        reviews = app.get('review_count', '?')
        dev = app.get('developer', '?')
        print(f"  ✓ {app['name']}: rating={rating}, reviews={reviews}, dev={dev}, features={len(app.get('features', []))}")
    
    # Save parsed data
    with open('/tmp/shopify_parsed.json', 'w') as f:
        json.dump(APP_TARGETS, f, indent=2)
    
    # Now extract reviews for each app using the browser
    print("\n" + "=" * 60)
    print("REVIEW EXTRACTION")
    print("=" * 60)
    print("I'll now use the browser to extract reviews for each app.")
    print("This requires interactive browser sessions.")
    print("\nFirst, let me get the correct review page URLs from the browser:")
    
    # I'll handle review extraction separately via browser
    return APP_TARGETS

if __name__ == '__main__':
    apps = main()
    print(f"\nSaved {len(apps)} app records to /tmp/shopify_parsed.json")
