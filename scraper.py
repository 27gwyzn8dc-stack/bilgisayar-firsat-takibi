import asyncio
import hashlib
import json
import logging
import random
import re
from urllib.parse import urljoin, urlsplit
import httpx
from bs4 import BeautifulSoup
from engine import parse_price
from identity import component_key

log = logging.getLogger(__name__)
AGENTS = ['LaptopPriceMonitor/1.0', 'LaptopPriceMonitor/1.0 (+price-history)']
BLOCKS = ('<title>just a moment', '<title>access denied', 'cf-chl-widget')

def valid_url(url, hosts):
    p = urlsplit(url)
    return p.scheme == 'https' and p.hostname in hosts and not p.username and p.port in (None, 443)

def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)

def extract(html, url, source):
    soup = BeautifulSoup(html, 'html.parser')
    candidates = []
    if source.get('adapter') == 'teknobiyotik':
        root = soup.select_one('#product_addtocart_form')
        if root:
            title = root.select_one('h1')
            price = root.select_one('.price-box .special-price .price') or root.select_one('.price-box .regular-price .price')
            button = root.select_one('.add-to-cart button.btn-cart')
            code = re.search(r'Ürün Kodu\s*:\s*([A-Za-z0-9._/-]+)', root.get_text(' ', strip=True))
            if title and price and button and not button.has_attr('disabled') and code:
                candidates.append({'@type':'Product','name':title.get_text(' ',strip=True),'sku':code[1],
                    'offers':{'@type':'Offer','price':price.get_text(strip=True),'priceCurrency':'TRY',
                              'availability':'https://schema.org/InStock','url':url}})
    if source.get('adapter') == 'vatan':
        title_tag = soup.select_one('h1.product-list__product-name')
        code = soup.select_one('.product-id[data-productcode]')
        price_tag = soup.select_one('.product-list__price')
        button = soup.select_one('#add-to-cart-button')
        if title_tag and code and price_tag and button and not button.has_attr('disabled'):
            candidates.append({'@type':'Product','name':title_tag.get_text(' ',strip=True),
                'sku':code['data-productcode'],'offers':{'@type':'Offer','price':price_tag.get_text(strip=True),
                'priceCurrency':'TRY','availability':'https://schema.org/InStock','url':url}})
    # GPN gibi mağazalar JSON-LD yerine schema.org microdata kullanır.
    if source.get('microdata'):
        for root in soup.select('[itemtype$="/Product"]'):
            def field(node, name):
                tag = node.select_one('[itemprop="'+name+'"]')
                return (tag.get('content') or tag.get('href') or tag.get('src') or tag.get_text(' ',strip=True)) if tag else ''
            offer_root = root.select_one('[itemprop="offers"]')
            if offer_root:
                candidates.append({'@type':'Product','name':field(root,'name'),'sku':field(root,'sku'),
                    'image':field(root,'image'),'gtin13':field(root,'Gtin13'),
                    'offers':{'@type':'Offer','price':field(offer_root,'price'),
                    'priceCurrency':field(offer_root,'priceCurrency'),'availability':field(offer_root,'availability'),
                    'itemCondition':field(offer_root,'itemCondition'),'url':url}})
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            candidates.extend(walk(json.loads(script.get_text())))
        except (ValueError, TypeError):
            continue
    for product in candidates:
        types = product.get('@type', [])
        if isinstance(types, str): types = [types]
        if 'Product' not in types:
            continue
        declared_url = product.get('url')
        if declared_url and urljoin(url,declared_url).split('?')[0].rstrip('/') != url.split('?')[0].rstrip('/'):
            continue  # Önerilen aksesuar ve yan ürünleri ana ürün fiyatı sanma.
        title = str(product.get('name', ''))
        if not re.search(source.get('title_pattern', r'(?i)laptop|notebook|dizüstü|macbook|masaüstü|oyuncu bilgisayar|ekran kart|işlemci|anakart|ddr[345]|ssd|güç kayna|psu|\bkasa\b|soğutucu'), title):
            continue
        sku = str(product.get('mpn') or product.get('sku') or '')
        if not sku: continue  # Başlık benzerliği ürün eşleştirmek için yeterli değil.
        if source['name'] == 'MediaMarkt':
            expected = re.search(r'-(\d+)\.html', url)
            if not expected or str(product.get('sku')) != expected.group(1):
                continue
        offers = product.get('offers', [])
        if isinstance(offers, dict): offers = [offers]
        for offer in offers:
            if not isinstance(offer, dict) or offer.get('@type') != 'Offer': continue
            if offer.get('priceCurrency') != 'TRY': continue
            if str(offer.get('availability', '')).split('/')[-1] != 'InStock': continue
            condition = str(offer.get('itemCondition', '')).split('/')[-1]
            if condition and condition != 'NewCondition': continue
            seller_data = offer.get('seller', {})
            seller = seller_data.get('name', '') if isinstance(seller_data, dict) else ''
            seller = seller or source.get('direct_seller', '')
            if seller not in source.get('trusted_sellers', []): continue
            offer_url = urljoin(url, offer.get('url') or product.get('url') or url)
            if not valid_url(offer_url, source['hosts']): continue
            try: price = parse_price(offer.get('price'))
            except ValueError: continue
            if source.get('adapter') == 'gaming':
                # Bu sitenin JSON-LD fiyatı gözlenen sayfada KDV hariçti.
                visible = soup.select_one('.summary p.price')
                if not visible: continue
                amounts = visible.select('ins .amount') or visible.select('.amount')
                try: price = max(parse_price(t.get_text(strip=True)) for t in amounts)
                except (ValueError,TypeError): continue
            picture = product.get('image', '')
            if isinstance(picture, list): picture = picture[0] if picture else ''
            if isinstance(picture, dict): picture = picture.get('url', '')
            # Satıcı ve SKU değişirse geçmiş karışmaz; yapılandırılmış SKU üretici modeliyle kontrol edilmeli.
            key = '|'.join([source['name'], seller, sku, offer_url.split('?')[0], 'price-v2'])
            comparison_key = source.get('comparison_keys', {}).get(offer_url.split('?')[0], '')
            comparison_key = comparison_key or component_key(title)
            gtin = str(product.get('gtin13') or product.get('gtin') or '')
            if not comparison_key and len(gtin) == 13 and gtin.isdigit():
                check = (10-sum(int(c)*(1 if i%2==0 else 3) for i,c in enumerate(gtin[:12]))%10)%10
                if check == int(gtin[-1]):
                    comparison_key = 'gtin13:'+gtin
            seller_id = source.get('seller_ids', {}).get(seller, seller.casefold().strip())
            yield dict(id=hashlib.sha256(key.encode()).hexdigest(), title=title[:500],
                       sku=sku, seller=seller, site=source['name'], url=offer_url,
                       comparison_key=comparison_key, seller_id=seller_id,
                       image=picture if isinstance(picture, str) and picture.startswith('https://') else '', price=price)

class Scraper:
    def __init__(self, config):
        self.config = config
        self.client = httpx.AsyncClient(timeout=25, follow_redirects=False,
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4))
        self.semaphore = asyncio.Semaphore(3)
        self.reports = {}

    async def close(self): await self.client.aclose()

    async def fetch(self, url, source):
        if not valid_url(url, source['hosts']): raise ValueError('Alan adı izin listesinde değil')
        for attempt in range(3):
            await asyncio.sleep(random.uniform(2, 5) + attempt * 3)
            try:
                response = await self.client.get(url, headers={'User-Agent': random.choice(AGENTS), 'Accept-Language': 'tr-TR,tr;q=0.9'})
                if response.status_code in (403, 401):
                    raise ValueError('Erişim engeli; koruma aşılmıyor')
                if response.status_code == 429 or response.status_code >= 500:
                    try: delay = min(120, max(1, int(response.headers.get('Retry-After', 2 ** (attempt + 2)))))
                    except ValueError: delay = 15
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
                if len(response.content) > 5_000_000: raise ValueError('Sayfa boyutu sınırı')
                html = response.text
                if any(marker in html.lower() for marker in BLOCKS): raise ValueError('Bot doğrulama sayfası')
                return html
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 2: raise
        raise ValueError('Yeniden deneme sınırı')

    async def render(self, url, source):
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page(locale='tr-TR')
                response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                if not valid_url(page.url, source['hosts']) or not response or response.status >= 400:
                    raise ValueError('Tarayıcı erişim hatası')
                await page.wait_for_timeout(2000)
                html = await page.content()
                if any(marker in html.lower() for marker in BLOCKS): raise ValueError('Tarayıcı bot engeli')
                return html
            finally: await browser.close()

    async def scan(self, source):
        async with self.semaphore:
            report = {'errors':0,'pages':0,'discovered':0,'last_error':None}
            self.reports[source['name']] = report
            urls = set(source.get('product_urls', []))
            groups = [sorted(urls)] if urls else []
            for listing in source.get('listing_urls', []):
                try:
                    soup = BeautifulSoup(await self.fetch(listing, source), 'html.parser')
                    group = set()
                    for anchor in soup.select(source.get('link_selector', 'a[href]')):
                        link = urljoin(listing, anchor.get('href', '').strip())
                        if valid_url(link, source['hosts']) and re.search(source['product_url_pattern'], link): group.add(link.split('#')[0])
                    urls.update(group)
                    if group: groups.append(sorted(group))
                except Exception as exc:
                    report['errors'] += 1
                    report['last_error'] = str(exc)[:150]
                    log.warning('listing_failed site=%s type=%s', source['name'], type(exc).__name__)
            seen = set()
            report['discovered'] = len(urls)
            # Döngüler arasında kaydır: aynı ilk 30 üründe takılı kalma.
            from pathlib import Path
            cursor_file = Path('data') / ('cursor-'+hashlib.sha256(source['name'].encode()).hexdigest()[:12]+'.txt')
            try: cursor = int(cursor_file.read_text())
            except (OSError,ValueError): cursor = 0
            # Kategorileri sırayla ziyaret et: laptoplar parçaların önünü kapatmasın.
            selected = []
            for step in range(max((len(g) for g in groups), default=0)):
                for group in groups:
                    candidate = group[(cursor + step) % len(group)]
                    if candidate not in selected: selected.append(candidate)
                    if len(selected) >= source.get('max_products',30): break
                if len(selected) >= source.get('max_products',30): break
            cursor_file.write_text(str(cursor + max(1, len(selected)//max(1,len(groups)))))
            for url in selected:
                try:
                    html = await self.fetch(url, source)
                    report['pages'] += 1
                    items = list(extract(html, url, source))
                    if not items and self.config.browser and source.get('render', False):
                        items = list(extract(await self.render(url, source), url, source))
                    if not items: log.warning('no_verified_offer site=%s url=%s', source['name'], url)
                    for item in items:
                        if item['id'] not in seen:
                            seen.add(item['id'])
                            yield item
                except Exception as exc:
                    report['errors'] += 1
                    report['last_error'] = str(exc)[:150]
                    log.warning('product_failed site=%s type=%s url=%s', source['name'], type(exc).__name__, url)
