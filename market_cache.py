"""Farklı tarama sıralarındaki teklifleri en fazla bir saat birleştirir."""
import json
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone, timedelta

def merge_offers(current, path=Path('data/market-cache.json')):
    now = datetime.now(timezone.utc)
    cached = {}
    try:
        for item in json.loads(path.read_text(encoding='utf-8')):
            when = datetime.fromisoformat(item['checked_at'])
            if now-timedelta(hours=1) <= when <= now:
                item['price'] = Decimal(item['price'])
                cached[item['id']] = item
    except (OSError, ValueError, KeyError, TypeError):
        cached = {}
    for item in current:
        cached[item['id']] = {**item, 'checked_at':now.isoformat()}
    path.write_text(json.dumps(list(cached.values()),default=str,ensure_ascii=False),encoding='utf-8')
    return list(cached.values())
