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

def scrape_eol_score_lines():
    """Scrape score lines from eol.cn (structured HTML tables)"""
    import requests, re
    from bs4 import BeautifulSoup
    
    print('\n=== Scraping eol.cn score lines ===')
    url = 'https://gaokao.eol.cn/e_html/gk/fsx/index.shtml'
    try:
        r = requests.get(url, headers={'User-Agent': UA}, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
    except Exception as e:
        print(f'  Error loading page: {e}')
        return []
    
    records = []
    current_province = ''
    current_year = 2025
    
    # Province names (to detect from surrounding context)
    prov_names = ['北京','天津','上海','重庆','河北','山西','辽宁','吉林','黑龙江','江苏','浙江','安徽','福建','江西','山东','河南','湖北','湖南','广东','广西','海南','四川','贵州','云南','西藏','陕西','甘肃','青海','宁夏','新疆','内蒙古']
    
    # Walk all elements - find province headings then extract their tables
    all_elems = list(soup.find_all(['h1','h2','h3','h4','strong','table','p','div']))
    
    for i, elem in enumerate(all_elems):
        if elem.name in ['h1','h2','h3','h4','strong']:
            text = elem.get_text(strip=True)
            for p in prov_names:
                if p in text:
                    current_province = p
                    ym = re.search(r'20\d{2}', text)
                    if ym:
                        current_year = int(ym.group())
                    break
        elif elem.name == 'table' and current_province:
            rows = elem.find_all('tr')
            if len(rows) < 2:
                continue
            # Check this table has score numbers
            all_text = elem.get_text()
            if not re.search(r'\d{3}', all_text):
                continue
            # Simple approach: first column = batch, find column with 3-digit numbers = score
            for row in rows[1:]:
                cells = [c.get_text(strip=True) for c in row.find_all(['th','td'])]
                if len(cells) < 2:
                    continue
                # Find column with 3-digit score
                for j in range(1, len(cells)):
                    m = re.search(r'\d{3}', cells[j])
                    if m:
                        score = int(m.group())
                        batch = cells[0] if cells[0] else cells[j-1] if j > 0 else ''
                        if 100 <= score <= 750:
                            record = {
                                'province': current_province,
                                'year': current_year,
                                'batch': batch,
                                'min_score': score,
                                'source': 'eol.cn',
                                'source_url': url,
                                'updated_at': datetime.now().isoformat()
                            }
                            records.append(record)
    
    print(f'  Extracted {len(records)} score line records')
    return records
def main():
    import argparse
    parser = argparse.ArgumentParser(description='Gaokao Data Updater')
    parser.add_argument('--limit', type=int, default=5, help='Max dxsbb articles')
    parser.add_argument('--push', action='store_true', help='Auto git push')
    parser.add_argument('--source', choices=['dxsbb','eol','all'], default='all', help='Data source')
    args = parser.parse_args()

    print(f'========== Gaokao Data Updater ==========')
    print(f'Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'Source: {args.source}')

    existing = load_json('admissions.json') or []
    new_count = 0

    # --- EOL.CN ---
    if args.source in ('eol', 'all'):
        eol_records = scrape_eol_score_lines()
        eol_dedup = {}
        for a in existing:
            if isinstance(a, dict):
                k = f"eol_{a.get('province','')}_{a.get('year','')}_{a.get('batch','')}"
                eol_dedup[k] = True
        added = 0
        for rec in eol_records:
            k = f"eol_{rec.get('province','')}_{rec.get('year','')}_{rec.get('batch','')}"
            if k not in eol_dedup:
                rec['source_url'] = 'https://gaokao.eol.cn/e_html/gk/fsx/index.shtml'
                existing.append(rec)
                eol_dedup[k] = True
                added += 1
        new_count += added
        print(f'  EOL: {len(eol_records)} extracted, {added} new records added')

    # --- DXSBB ---
    if args.source in ('dxsbb', 'all'):
        print('=== DXSBB ===')
        existing_urls = set()
        for a in existing:
            if isinstance(a, dict) and 'source_url' in a:
                existing_urls.add(a['source_url'])
        articles = scrape_dxsbb_list()
        articles = articles[:args.limit]
        print(f'  Parsing {len(articles)} articles...')
        for i, art in enumerate(articles):
            if art['url'] in existing_urls:
                continue
            print(f'  [{i+1}/{len(articles)}] {art["title"][:50]}')
            records = scrape_dxsbb_article(art)
            for rec in records:
                rec['source_url'] = art['url']
                rec['source_title'] = art['title']
                rec['updated_at'] = datetime.now().isoformat()
                existing.append(rec)
                new_count += 1
            print(f'    -> {len(records)} records')
            time.sleep(0.5)

    # --- SAVE ---
    if new_count > 0:
        save_json('admissions.json', existing)
        print(f'=== RESULT: +{new_count} new records, {len(existing)} total ===')
        if args.push:
            git_push(f'Auto update: +{new_count} records')
    else:
        print('No new records. Data is up to date.')

    print('Done!')
if __name__ == '__main__':
    main()

# ===== EOL.CN SCRAPER =====

