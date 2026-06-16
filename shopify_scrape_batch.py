#!/usr/bin/env python3
"""
Shopify App Store scraper - batch processor.
Processes page text and saves to combined CSV.
"""
import re
import csv

def parse_page_text(text):
    apps = []
    results_idx = text.find('Results for')
    if results_idx < 0:
        return apps
    text = text[results_idx:]
    # Cut at footer
    for marker in ['Security essentials', 'Want to add an app']:
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx]
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines:
        return apps
    while lines and (lines[0].startswith('Built for') or lines[0] == 'Refine' or re.match(r'^\d+ apps?$', lines[0])):
        lines.pop(0)
    i = 0
    current_app = {}
    state = 'init'
    while i < len(lines):
        line = lines[i]
        if state == 'init':
            if line in ['Built for Shopify', '•']:
                i += 1; continue
            if re.match(r'^Results for', line) or re.match(r'^\d+ apps?$', line):
                i += 1; continue
            if len(line) > 3 and not re.match(r'^[\d]\.', line):
                current_app = {'name': line, 'rating': '', 'reviews': '', 'price': '', 'description': ''}
                state = 'name'
            i += 1; continue
        elif state == 'name':
            if re.match(r'^[\d]\.[\d]$', line):
                current_app['rating'] = line; state = 'rating'
            elif line in ['Built for Shopify', '•']:
                pass
            elif len(line) > 3 and not re.match(r'^[\d]', line):
                if current_app.get('name') and current_app.get('rating'):
                    apps.append(current_app)
                current_app = {'name': line, 'rating': '', 'reviews': '', 'price': '', 'description': ''}
                state = 'name'
            i += 1; continue
        elif state == 'rating':
            if 'out of' in line and 'stars' in line:
                i += 1; continue
            if line == '•':
                i += 1; continue
            m = re.search(r'\(([\d,]+)\)', line)
            if m:
                current_app['reviews'] = m.group(1).replace(',', ''); state = 'reviews'; i += 1; continue
            m = re.match(r'^([\d,]+) total reviews', line)
            if m:
                current_app['reviews'] = m.group(1).replace(',', ''); state = 'reviews'; i += 1; continue
            i += 1; continue
        elif state == 'reviews':
            if line == '•':
                i += 1; continue
            m = re.match(r'^([\d,]+) total reviews', line)
            if m:
                i += 1; continue
            if re.match(r'^Free (trial|plan|to install)', line):
                current_app['price'] = line; state = 'price'
            elif 'Free' in line and len(line) < 50:
                current_app['price'] = line; state = 'price'
            elif not current_app.get('price') and len(line) < 50 and line != '•':
                current_app['price'] = line; state = 'price'
            i += 1; continue
        elif state == 'price':
            current_app['description'] = line
            apps.append(current_app)
            current_app = {}; state = 'init'
            i += 1; continue
    if current_app.get('name') and current_app.get('rating') and current_app.get('reviews'):
        apps.append(current_app)
    return apps

def dedup(apps):
    seen = {}
    result = []
    for app in apps:
        name = app['name'].lower().strip()
        if name not in seen:
            seen[name] = True
            result.append(app)
    return result

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 shopify_scrape_batch.py <page1.txt> [page2.txt ...]")
        sys.exit(1)
    
    all_apps = []
    for filepath in sys.argv[1:]:
        with open(filepath, 'r') as f:
            text = f.read()
        apps = parse_page_text(text)
        print(f"  {filepath}: {len(apps)} apps")
        all_apps.extend(apps)
    
    unique = dedup(all_apps)
    print(f"\nTotal unique: {len(unique)}")
    
    # Save to CSV
    with open('/Users/yahya/shopify_fraud_apps.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['App_Name', 'Rating', 'Reviews', 'Price', 'Description'])
        for app in unique:
            writer.writerow([app.get('name', ''), app.get('rating', ''), app.get('reviews', ''), app.get('price', ''), app.get('description', '')])
    
    print(f"Saved to /Users/yahya/shopify_fraud_apps.csv")
