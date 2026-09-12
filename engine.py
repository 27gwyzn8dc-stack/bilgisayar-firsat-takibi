import re
from decimal import Decimal, InvalidOperation
from statistics import median

def parse_price(value) -> Decimal:
    """Türkçe ve JSON-LD fiyatlarını kuruş hassasiyetinde çözer; aralıkları reddeder."""
    if isinstance(value, bool) or value is None:
        raise ValueError('Fiyat yok')
    s = str(value).strip().replace('\xa0', ' ')
    s = re.sub(r'(?i)(TRY|TL|₺)', '', s).strip().replace(' ', '')
    if not re.fullmatch(r'\d+(?:[.,]\d+)*', s):
        raise ValueError('Belirsiz fiyat')
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):
            if not re.fullmatch(r'\d{1,3}(?:\.\d{3})+,\d{1,2}', s):
                raise ValueError('Geçersiz gruplama')
            s = s.replace('.', '').replace(',', '.')
        else:
            if not re.fullmatch(r'\d{1,3}(?:,\d{3})+\.\d{1,2}', s):
                raise ValueError('Geçersiz gruplama')
            s = s.replace(',', '')
    elif ',' in s or '.' in s:
        separator = ',' if ',' in s else '.'
        parts = s.split(separator)
        if len(parts) == 2 and len(parts[-1]) in (1, 2):
            s = '.'.join(parts)
        elif len(parts[0]) <= 3 and all(len(p) == 3 for p in parts[1:]):
            s = ''.join(parts)
        else:
            raise ValueError('Geçersiz gruplama')
    try:
        price = Decimal(s).quantize(Decimal('.01'))
    except InvalidOperation as exc:
        raise ValueError('Geçersiz fiyat') from exc
    if price <= 0:
        raise ValueError('Fiyat pozitif olmalı')
    return price

def evaluate(price, history, now, config):
    # Her güne tek oy: sık taranan günler referansı şişiremez.
    days = {}
    for observed_at, old_price in history:
        if observed_at.date() < now.date():
            days.setdefault(observed_at.date(), []).append(old_price)
    if len(days) < config.min_days or len(history) < config.min_samples:
        return None
    reference = Decimal(median([median(v) for v in days.values()]))
    discount = (reference - price) / reference * 100
    if reference >= config.min_reference and (not config.max_price or price <= config.max_price) and discount >= config.min_discount:
        return reference, discount.quantize(Decimal('.01'))
    return None

def market_deal(item, offers, config):
    """Bugünkü aynı konfigürasyon teklifleri; fiyat geçmişi iddiasında bulunmaz."""
    key = item.get('comparison_key')
    if not config.market_enabled or not key:
        return None
    sellers = {}
    for other in offers:
        if other.get('comparison_key') != key or other['seller_id'] == item['seller_id']:
            continue
        # Aynı satıcının farklı pazaryeri ilanları tek referanstır.
        previous = sellers.get(other['seller_id'])
        if previous is None or other['price'] < previous['price']:
            sellers[other['seller_id']] = other
    peers = list(sellers.values())
    if len(peers) < config.min_market_sellers or len({p['site'] for p in peers}) < 2:
        return None
    prices = [p['price'] for p in peers]
    # Referanslar çok dağınıksa ürün eşleşmesi / şişirilmiş fiyat riski var.
    if max(prices) / min(prices) > Decimal('1.25'):
        return None
    reference = Decimal(median(prices))
    discount = (reference-item['price']) / reference * 100
    # Medyana göre ucuz görünse de bir başka satıcı zaten ucuzsa alarm verme.
    if reference < config.min_reference or (config.max_price and item['price'] > config.max_price):
        return None
    if discount < config.min_discount or item['price'] > min(prices) * (1-config.min_discount/100):
        return None
    return reference, discount.quantize(Decimal('.01')), [{'seller':p['seller'], 'price':str(p['price']), 'url':p['url']} for p in peers]
