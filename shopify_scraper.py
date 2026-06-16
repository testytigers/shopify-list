#!/usr/bin/env python3
"""
Shopify App Store Competitor Scraper
Extracts app metadata and reviews for fraud/bot prevention apps.
"""
import subprocess
import json
import re
import csv
import time
import os
from html.parser import HTMLParser

def curl_fetch(url, ua=None):
    """Fetch a URL using curl."""
    cmd = ['curl', '-s', '-L', '--max-time', '30',
           '-A', ua or 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
           url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def extract_json_ld(html):
    """Extract JSON-LD structured data from HTML."""
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None

def extract_meta_tags(html):
    """Extract meta tags."""
    tags = {}
    for match in re.finditer(r'<meta\s+name="([^"]+)"\s+content="([^"]*)"', html):
        tags[match.group(1)] = match.group(2)
    # Also get og: tags
    for match in re.finditer(r'<meta\s+property="([^"]+)"\s+content="([^"]*)"', html):
        tags[match.group(1)] = match.group(2)
    return tags

def extract_description(html):
    """Extract meta description."""
    match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
    return match.group(1) if match else ''

def extract_pricing_from_html(html):
    """Extract pricing information from the page."""
    pricing = []
    # Look for pricing sections
    price_matches = re.findall(r'<span[^>]*>([^<]*(?:\$[\d.]+/month|\$[\d.]+/year|Free[^<]*)[^<]*)</span>', html)
    for match in price_matches:
        pricing.append(match.strip())
    
    # Look for pricing headers
    price_headers = re.findall(r'<h[1-6][^>]*>([^<]*(?:Free|\$[\d.]+)[^<]*)</h[1-6]>', html)
    pricing.extend(price_headers)
    
    # Look for pricing plan cards
    plan_matches = re.findall(r'(?:Free|Premium|Basic|Pro|Enterprise)\s*(?:plan|to install|trial)?', html, re.IGNORECASE)
    
    return list(set(pricing))[:5]

def extract_features_from_html(html):
    """Extract feature lists from the page."""
    features = []
    # Look for list items with bullet points or feature descriptions
    list_items = re.findall(r'<li[^>]*>(.*?)</li>', html, re.DOTALL)
    for item in list_items:
        # Clean HTML tags
        text = re.sub(r'<[^>]+>', '', item).strip()
        text = re.sub(r'\s+', ' ', text)
        if len(text) > 20 and len(text) < 500:
            # Filter out navigation and footer content
            skip_patterns = ['Sales channels', 'Finding products', 'Selling products', 
                           'Orders and shipping', 'Store design', 'Marketing and conversion',
                           'Store management', 'Browse apps', 'Log in', 'Start for free',
                           'App categories', 'Top categories', 'Dropshipping', 'Marketplaces',
                           'Product reviews', 'Email marketing', 'SEO', 'Shipping',
                           'Currency and translation', 'Shopify Help Center', 
                           'API documentation', 'Shopify Community', 'Community Events',
                           'Shopify Blog', 'Research', 'About', 'Careers', 'Investors',
                           'Developer login', 'Terms of service', 'Privacy policy',
                           'California Consumer Privacy Act', 'Change your language']
            if not any(p in text for p in skip_patterns):
                features.append(text)
    
    return features[:10]

# Define the target apps and their search queries
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

def fetch_app_metadata(app):
    """Fetch metadata for a single app."""
    url = app['url']
    html = curl_fetch(url)
    
    if not html:
        print(f"  [!] Empty response for: {app['name']}")
        app['status'] = 'empty'
        return False
    
    # Check the title for 404/not found
    title_match = re.search(r'<title>([^<]+)</title>', html)
    if title_match:
        title = title_match.group(1)
        if '404' in title or 'not found' in title.lower() or 'does not exist' in title.lower():
            print(f"  [!] {app['name']}: 404 ({title})")
            app['status'] = '404'
            return False
    
    # If page is very short or missing key elements
    if len(html) < 5000:
        print(f"  [!] {app['name']}: Page too short ({len(html)} chars)")
        app['status'] = 'short'
        return False
    
    # Extract JSON-LD
    ld = extract_json_ld(html)
    
    # Extract meta tags
    meta = extract_meta_tags(html)
    
    # Extract description
    desc = extract_description(html)
    
    # Extract pricing
    pricing = extract_pricing_from_html(html)
    
    # Extract features
    features = extract_features_from_html(html)
    
    # Parse key data
    app['status'] = 'ok'
    app['html_length'] = len(html)
    
    if ld and isinstance(ld, dict):
        app['rating'] = ld.get('aggregateRating', {}).get('ratingValue', '')
        app['review_count'] = ld.get('aggregateRating', {}).get('ratingCount', '')
        app['category'] = ld.get('applicationCategory', '')
        app['operating_system'] = ld.get('operatingSystem', '')
    
    if ld and isinstance(ld, list):
        for item in ld:
            if item.get('@type') == 'SoftwareApplication':
                app['rating'] = item.get('aggregateRating', {}).get('ratingValue', '')
                app['review_count'] = item.get('aggregateRating', {}).get('ratingCount', '')
                app['category'] = item.get('applicationCategory', '')
    
    app['description'] = desc
    
    # Try to extract developer name from the page
    dev_match = re.search(r'Developer.*?>(.*?)<', html)
    if dev_match:
        app['developer'] = dev_match.group(1).strip()
    
    # Look for developer in JSON-LD
    if ld and isinstance(ld, dict):
        brand = ld.get('brand', '')
        if brand:
            app['developer'] = app.get('developer', brand)
    
    # Look for pricing more thoroughly
    pricing_text = re.findall(r'(?:\$[\d.]+/\s*month|Free\s*(?:to\s*install|plan|trial)|\$[\d.]+/\s*year)', html, re.IGNORECASE)
    if pricing_text:
        app['pricing'] = list(set(pricing_text))[:5]
    else:
        app['pricing'] = pricing[:3]
    
    app['features'] = features
    
    return True

def main():
    print("=" * 60)
    print("Shopify App Store - Fraud & Bot Prevention Competitor Scraper")
    print("=" * 60)
    
    # Phase 1: Fetch metadata for all apps
    print("\n[Phase 1] Fetching app metadata...")
    for i, app in enumerate(APP_TARGETS):
        print(f"\n[{i+1}/{len(APP_TARGETS)}] Fetching: {app['name']}")
        success = fetch_app_metadata(app)
        time.sleep(0.5)  # Rate limiting
    
    # Print summary
    print("\n" + "=" * 60)
    print("METADATA SUMMARY")
    print("=" * 60)
    for app in APP_TARGETS:
        print(f"\n  {app['name']}:")
        print(f"    Status: {app.get('status', 'unknown')}")
        print(f"    Rating: {app.get('rating', 'N/A')}")
        print(f"    Reviews: {app.get('review_count', 'N/A')}")
        print(f"    Developer: {app.get('developer', 'N/A')}")
        print(f"    Pricing: {app.get('pricing', 'N/A')}")
        print(f"    Features: {len(app.get('features', []))} found")
        if app.get('description'):
            print(f"    Description: {app['description'][:100]}...")
    
    # Save metadata to JSON
    with open('/tmp/shopify_metadata.json', 'w') as f:
        json.dump(APP_TARGETS, f, indent=2)
    
    print(f"\n[✓] Metadata saved to /tmp/shopify_metadata.json")
    
    # Phase 2: Extract reviews using browser
    print("\n[Phase 2] Reviews will be extracted via browser...")
    print("  (This requires interactive browser sessions for each app)")
    print(f"  Apps with reviews to scrape: {sum(1 for a in APP_TARGETS if a.get('status') == 'ok')}/ {len(APP_TARGETS)}")
    
    # Initial CSV with metadata
    print("\n[Phase 3] Creating initial CSV...")
    create_initial_csv(APP_TARGETS)
    
    print("\n[✓] Done! Check shopify_security_competitors.csv")

def create_initial_csv(apps):
    """Create initial CSV with metadata only."""
    fieldnames = [
        'App_Name', 'Developer_Name', 'Launch_Date', 'Last_Update',
        'Pricing_Plans', 'Total_Reviews_Count', 'Avg_Rating', 'Feature_List',
        'Reviewer_Name', 'Reviewer_Location', 'Duration_Of_Use',
        'Review_Rating', 'Review_Date', 'Review_Text', 'Developer_Response'
    ]
    
    with open('/Users/yahya/shopify_security_competitors.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(fieldnames)
        
        for app in apps:
            if app.get('status') != 'ok':
                continue
            
            features_str = '; '.join(app.get('features', [])[:10])
            pricing_str = '; '.join(app.get('pricing', ['N/A']))
            
            writer.writerow([
                app.get('name', ''),
                app.get('developer', ''),
                '',  # Launch_Date
                '',  # Last_Update
                pricing_str,
                app.get('review_count', ''),
                app.get('rating', ''),
                features_str,
                '',  # Reviewer_Name
                '',  # Reviewer_Location
                '',  # Duration_Of_Use
                '',  # Review_Rating
                '',  # Review_Date
                '',  # Review_Text
                ''   # Developer_Response
            ])

if __name__ == '__main__':
    main()
