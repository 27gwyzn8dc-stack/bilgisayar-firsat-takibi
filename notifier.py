import html
from datetime import datetime, timedelta
from decimal import Decimal
import httpx
from sqlalchemy import select
from database import Alert, Product

def message(p):
    e = lambda value: html.escape(str(value), quote=True)
    market = p.get('basis') == 'market'
    label = 'Piyasaya göre ucuz — geçmiş düşüşü doğrulanmadı' if market else 'Gözlenen geçmişe göre fiyat düşüşü'
    reference_label = 'Diğer satıcıların medyanı' if market else 'Geçmiş medyan'
    peers = ''.join(f"\n{e(x['seller'])}: {e(x['price'])} TL" for x in p.get('peers', [])[:5])
    return (f"<b>{label}</b>\n{e(p['title'])}\n"
            f"{reference_label}: {e(p['reference'])} TL\n<b>Yeni: {e(p['price'])} TL</b>\n"
            f"{'Fiyat farkı' if market else 'Düşüş'}: %{e(p['discount'])}\nSatıcı: {e(p['seller'])}\n"
            f"Model/SKU: {e(p['sku'])}\n<a href=\"{e(p['url'])}\">Ürünü aç</a>{peers}")

async def dispatch(db, config):
    # Tek dispatcher: Telegram tam exactly-once garantisi sunmaz; belirsiz timeout tekrara yol açabilir.
    if config.dry_run: return
    async with db.sessions() as session:
        ids = (await session.scalars(select(Alert.id).where(Alert.status == 'pending', Alert.next_attempt <= datetime.utcnow()).limit(30))).all()
    async with httpx.AsyncClient(timeout=20) as client:
        for alert_id in ids:
            async with db.sessions.begin() as session:
                alert = await session.get(Alert, alert_id)
                if not alert or alert.status != 'pending': continue
                if datetime.utcnow() - alert.created_at > timedelta(minutes=30):
                    alert.status = 'expired'
                    continue
                text = message(alert.payload)
                photo = alert.payload.get('image')
                method = 'sendPhoto' if photo and len(text) <= 1000 else 'sendMessage'
                body = {'chat_id': config.chat_id, 'parse_mode': 'HTML'}
                body.update({'photo': photo, 'caption': text} if method == 'sendPhoto' else {'text': text})
                try:
                    if config.provider == 'ntfy':
                        import re
                        plain = html.unescape(re.sub(r'<[^>]+>', '', text))
                        response = await client.post('https://ntfy.sh', json={
                            'topic': config.ntfy_topic, 'title': 'Bilgisayar firsat alarmi',
                            'message': plain, 'click': alert.payload['url'], 'priority': 4,
                        })
                        response.raise_for_status()
                        receipt = response.json()
                        if receipt.get('event') != 'message' or not receipt.get('id'):
                            raise ValueError('ntfy bildirim makbuzu yok')
                        alert.status = 'sent'
                        product = await session.get(Product, alert.product_id)
                        product.last_alerted_price = Decimal(alert.payload['price'])
                        product.notification_sent_at = datetime.utcnow()
                        continue
                    response = await client.post(f'https://api.telegram.org/bot{config.token}/{method}', json=body)
                    data = response.json()
                    # Telegram görseli okuyamazsa aynı metinle devam et.
                    if method == 'sendPhoto' and response.status_code == 400:
                        response = await client.post(f'https://api.telegram.org/bot{config.token}/sendMessage', json={'chat_id': config.chat_id, 'parse_mode': 'HTML', 'text': text})
                        data = response.json()
                    if not data.get('ok'):
                        alert.attempts += 1
                        alert.next_attempt = datetime.utcnow() + timedelta(seconds=min(900, max(30, int(data.get('parameters', {}).get('retry_after', 60 * alert.attempts)))))
                        if response.status_code in (400, 401, 403) or alert.attempts >= 5: alert.status = 'failed'
                        continue
                    alert.status = 'sent'
                    product = await session.get(Product, alert.product_id)
                    product.last_alerted_price = Decimal(alert.payload['price'])
                    product.notification_sent_at = datetime.utcnow()
                except (httpx.HTTPError, ValueError):
                    alert.attempts += 1
                    alert.next_attempt = datetime.utcnow() + timedelta(minutes=2)
                    if alert.attempts >= 5: alert.status = 'failed'
