"""Yerel durum raporu; gizli ayarları veya kanal adını göstermez."""
from pathlib import Path
import json,html
from datetime import datetime,timezone

root=Path(__file__).parent
health=json.loads((root/'data/health.json').read_text(encoding='utf-8'))
offers=json.loads((root/'data/latest-offers.json').read_text(encoding='utf-8'))
e=lambda x:html.escape(str(x),quote=True)
rows=''.join('<tr>'+''.join('<td>'+e(s.get(k,''))+'</td>' for k in ['site','status','verified_offers','discovered','pages','errors'])+'</tr>' for s in health['sources'])
products=''.join(f'<tr><td>{e(p["site"])}</td><td><a href="{e(p["url"])}">{e(p["title"])}</a></td><td>{e(p["price"])} TL</td></tr>' for p in sorted(offers,key=lambda x:float(x['price'])))
output=root/'durum.html'
output.write_text('<!doctype html><meta charset="utf-8"><title>Bilgisayar fırsat takibi</title><style>body{font:16px system-ui;margin:40px;background:#101827;color:#eee}td,th{padding:12px;border-bottom:1px solid #456}a{color:#77ccff}table{width:100%}</style><h1>Bilgisayar fırsat takibi</h1><p>Son tarama UTC: '+e(health['last_cycle'])+'</p><p>Bu tablo fiyat gözlemleridir; fırsat listesi değildir. 403 dönen kaynaklar ve çapraz mağaza eşleştirmeleri tamamlanmamış olabilir.</p><table><tr><th>Kaynak</th><th>Durum</th><th>Teklif</th><th>Keşif</th><th>Sayfa</th><th>Hata</th></tr>'+rows+'</table><h2>Son gözlemler</h2><table>'+products+'</table>',encoding='utf-8')
print(output)
