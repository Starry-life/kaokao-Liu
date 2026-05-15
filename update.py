#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""update.py - 自动采集 & 网站更新"""
import json, os, sys, time, re
from datetime import datetime
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
def load_json(fname):
    p = os.path.join(DATA, fname)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else None

def save_json(fname, data):
    os.makedirs(DATA, exist_ok=True)
    p = os.path.join(DATA, fname)
    json.dump(data, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'  Saved: {p}')

def scrape_dxsbb_list():
    print('\n=== Scraping dxsbb.com article list ===')
    import requests
    from bs4 import BeautifulSoup
    articles = []
    for page in range(1, 6):
        url = 'https://www.dxsbb.com/news/list_458.html' if page == 1 else f'https://www.dxsbb.com/news/list_458_{page}.html'
        try:
            r = requests.get(url, headers={'User-Agent': UA}, timeout=15)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.content, 'html.parser', from_encoding='gb18030')
            found = 0
            for a in soup.select('.listBox a[href], .listBox2news a[href]'):
                href = a.get('href', '')
                title = a.get_text(strip=True)
                if href and title and '录取分数线' in title:
                    full_url = f'https://www.dxsbb.com{href}' if href.startswith('/') else href
                    articles.append({'title': title, 'url': full_url})
                    found += 1
            print(f'  Page {page}: {found} articles')
            if found == 0:
                break
            time.sleep(0.5)
        except Exception as e:
            print(f'  Page {page} error: {e}')
            break
    print(f'  Total: {len(articles)} articles found')
    return articles

def scrape_dxsbb_article(article):
    """Parse one dxsbb article, extract admission records"""
    import requests
    from bs4 import BeautifulSoup
    try:
        r = requests.get(article['url'], headers={'User-Agent': UA}, timeout=15)
        soup = BeautifulSoup(r.content, 'html.parser', from_encoding='gb18030')
        h1 = soup.find('h1')
        title_text = h1.text.strip() if h1 else ''
        match = re.search(r'\d{4}(.+?)录取分数线', title_text)
        school_name = match.group(1) if match else title_text[:20]
        records = []
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            if len(rows) < 2:
                continue
            header_cells = [c.get_text(strip=True) for c in rows[0].find_all(['th', 'td'])]
            col_map = {}
            for idx, h in enumerate(header_cells):
                if any(k in h for k in ['省份', '地区', '省市']):
                    col_map['province'] = idx
                elif any(k in h for k in ['年份', '年度', '时间']):
                    col_map['year'] = idx
                elif any(k in h for k in ['科类', '科目', '文理', '选科']):
                    col_map['category'] = idx
                elif any(k in h for k in ['批次', '录取批次']):
                    col_map['batch'] = idx
                elif any(k in h for k in ['最低分', '录取分', '分数线', '投档分']):
                    col_map['min_score'] = idx
                elif any(k in h for k in ['最低位次', '位次', '排名']):
                    col_map['min_rank'] = idx
                elif any(k in h for k in ['专业', '专业名称']):
                    col_map['major'] = idx
            if not col_map:
                continue
            for row in rows[1:]:
                cells = [c.get_text(strip=True) for c in row.find_all('td')]
                if not cells or len(cells) < 2:
                    continue
                record = {'school': school_name, 'source': 'dxsbb.com'}
                for key, idx in col_map.items():
                    if idx < len(cells):
                        val = cells[idx]
                        if key == 'year':
                            m = re.search(r'20\d{2}', val)
                            if m:
                                record[key] = int(m.group())
                        elif key == 'min_score':
                            try:
                                record[key] = int(float(val.replace(',', '')))
                            except:
                                record[key] = val
                        elif key == 'min_rank':
                            try:
                                record[key] = int(val.replace(',', '').replace('位', ''))
                            except:
                                pass
                        else:
                            record[key] = val
                if record.get('min_score'):
                    records.append(record)
        return records
    except Exception as e:
        print(f'    Parse error: {e}')
        return []

def git_push(message=None):
    import subprocess
    if message is None:
        message = f'Auto update: {datetime.now().strftime("%Y-%m-%d %H:%M")}'
    print(f'\n=== Git Push: {message} ===')
    dirs = ['data/', 'index.html']
    for item in dirs:
        target = os.path.join(HERE, item)
        if os.path.exists(target):
            subprocess.run(['git', 'add', item], cwd=HERE, capture_output=True)
    result = subprocess.run(['git', 'commit', '-m', message], cwd=HERE, capture_output=True, text=True)
    print(f'  Commit: {result.stdout.strip() or result.stderr.strip()}')
    result = subprocess.run(['git', 'push', 'origin', 'main'], cwd=HERE, capture_output=True, text=True)
    print(f'  Push: {result.stdout.strip() or result.stderr.strip()}')

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Gaokao Data Updater')
    parser.add_argument('--limit', type=int, default=5, help='Max articles to scrape')
    parser.add_argument('--push', action='store_true', help='Auto git push after update')
    args = parser.parse_args()

    print(f'========== Gaokao Data Updater ==========')
    print(f'Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')

    # 1. Scrape dxsbb
    print('\n[1/3] Collecting article list from dxsbb.com...')
    articles = scrape_dxsbb_list()
    articles = articles[:args.limit]

    # 2. Parse each article
    print(f'\n[2/3] Parsing {len(articles)} articles...')
    existing = load_json('admissions.json') or []
    existing_urls = set()
    for a in existing:
        if isinstance(a, dict) and 'source_url' in a:
            existing_urls.add(a['source_url'])

    new_count = 0
    for i, art in enumerate(articles):
        if art['url'] in existing_urls:
            print(f'  [{i+1}/{len(articles)}] SKIP: {art["title"][:50]}')
            continue
        print(f'  [{i+1}/{len(articles)}] Scraping: {art["title"][:50]}')
        records = scrape_dxsbb_article(art)
        for rec in records:
            rec['source_url'] = art['url']
            rec['source_title'] = art['title']
            rec['updated_at'] = datetime.now().isoformat()
            existing.append(rec)
            new_count += 1
        print(f'    -> {len(records)} records extracted')
        time.sleep(1)

    # 3. Save and optionally push
    print(f'\n[3/3] Saving results...')
    if new_count > 0:
        save_json('admissions.json', existing)
        print(f'\n=== RESULT ===')
        print(f'New records: {new_count}')
        print(f'Total records: {len(existing)}')
        if args.push:
            git_push(f'Auto update: +{new_count} admission records')
    else:
        print('No new records found. Data is up to date.')

    print('\nDone!')

if __name__ == '__main__':
    main()
