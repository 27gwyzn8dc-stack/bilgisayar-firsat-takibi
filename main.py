import argparse
import asyncio
import json
import logging
import random
import os
import httpx
from datetime import datetime, timezone
from pathlib import Path
from filelock import FileLock
from config import Config
from database import Database
from scraper import Scraper
from notifier import dispatch
from market_cache import merge_offers

log = logging.getLogger('monitor')

async def run(once=False):
    config = Config()
    config.validate()
    sources = json.loads(Path(config.sources_file).read_text(encoding='utf-8'))
    db, scraper = Database(config), Scraper(config)
    await db.init()
    async def scan(source):
        items = []
        try:
            async for item in scraper.scan(source):
                items.append(item)
        except Exception as exc:
            log.error('source_failed site=%s type=%s', source['name'], type(exc).__name__)
        report = scraper.reports.get(source['name'], {})
        return {'site': source['name'], 'verified_offers': len(items), **report,
                'status':'ok' if items else 'blocked_or_unverified'}, items
    try:
        while True:
            try:
                batches = await asyncio.gather(*(scan(s) for s in sources if s.get('enabled')))
                results = [batch[0] for batch in batches]
                offers = [item for batch in batches for item in batch[1]]
                if not offers:
                    raise RuntimeError('Hiçbir kaynaktan doğrulanmış fiyat alınamadı')
                comparisons = merge_offers(offers)
                queued_count = 0
                record_errors = 0
                for item in offers:
                    try:
                        queued = await db.record(item, comparisons)
                        queued_count += int(queued)
                        log.info('observed site=%s sku=%s price=%s alert=%s', item['site'], item['sku'], item['price'], queued)
                    except Exception as exc:
                        record_errors += 1
                        log.error('record_failed type=%s', type(exc).__name__)
                await dispatch(db, config)
                Path('data/health.json').write_text(json.dumps({'last_cycle': datetime.now(timezone.utc).isoformat(), 'sources': results, 'dry_run': config.dry_run},ensure_ascii=False), encoding='utf-8')
                Path('data/latest-offers.json').write_text(json.dumps(offers,default=str,ensure_ascii=False,indent=2),encoding='utf-8')
                import subprocess, sys
                subprocess.run([sys.executable, 'status.py'],timeout=20,check=False,capture_output=True)
                summary = '\n'.join(f"{r['site']}: {r['verified_offers']} fiyat, {r.get('errors',0)} hata" for r in results)
                log.info('scan_summary offers=%s queued=%s record_errors=%s',len(offers),queued_count,record_errors)
                if os.getenv('GITHUB_STEP_SUMMARY'):
                    Path(os.environ['GITHUB_STEP_SUMMARY']).write_text(
                        f'Toplam {len(offers)} stoklu fiyat. {queued_count} alarm kuyruğa alındı.\n\n'+summary.replace('\n','\n\n'),encoding='utf-8')
                if os.getenv('BOOTSTRAP') == 'true' and config.provider == 'ntfy' and not config.dry_run:
                    # İlk kurulum bildirimi fırsat gibi gösterilmez.
                    async with httpx.AsyncClient(timeout=20) as client:
                        response = await client.post('https://ntfy.sh',json={
                            'topic':config.ntfy_topic,'title':'Bulut fiyat takibi devrede',
                            'message':f'GitHub sunucusunda tarama tamamlandı. {len(offers)} stoklu fiyat okundu; {queued_count} fırsat alarmı kuyruğa alındı. Bu mesaj kurulum doğrulamasıdır.\n'+summary,
                            'click':'https://github.com/'+os.getenv('GITHUB_REPOSITORY','27gwyzn8dc-stack/bilgisayar-firsat-takibi')+'/actions', 'priority':3})
                        response.raise_for_status()
                        if not response.json().get('id'): raise RuntimeError('Bildirim kabul edilmedi')
                    log.info('cloud_setup_notification_accepted')
                if record_errors: raise RuntimeError('Bazı fiyatlar veritabanına kaydedilemedi')
            except Exception as exc:
                log.error('cycle_failed type=%s', type(exc).__name__)
                if once: raise
            if once: break
            # Kuyruk yeniden denemeleri tam tarama periyodunu beklemez.
            remaining = config.interval + random.randint(0, 60)
            while remaining > 0:
                await asyncio.sleep(min(30, remaining))
                remaining -= 30
                try: await dispatch(db, config)
                except Exception as exc: log.error('dispatch_failed type=%s', type(exc).__name__)
    finally:
        await scraper.close()
        await db.engine.dispose()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    logging.getLogger('httpx').setLevel(logging.WARNING)  # Bot tokeni URL loglarına düşmesin.
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    Path('data').mkdir(exist_ok=True)
    try:
        with FileLock('data/worker.lock', timeout=0): asyncio.run(run(args.once))
    except KeyboardInterrupt: pass
