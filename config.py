import os
from dataclasses import dataclass
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    database_url: str = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///data/prices.db')
    token: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    chat_id: str = os.getenv('CHAT_ID', '')
    provider: str = os.getenv('NOTIFICATION_PROVIDER', 'telegram')
    ntfy_topic: str = os.getenv('NTFY_TOPIC', '')
    dry_run: bool = os.getenv('DRY_RUN', 'true').lower() == 'true'
    interval: int = int(os.getenv('INTERVAL_SECONDS', '1200'))
    max_price: Decimal = Decimal(os.getenv('MAX_PRICE', '0'))  # 0: üst sınır yok
    min_reference: Decimal = Decimal(os.getenv('MIN_REFERENCE', '0'))
    min_discount: Decimal = Decimal(os.getenv('MIN_DISCOUNT_PERCENT', '15'))
    history_days: int = int(os.getenv('HISTORY_DAYS', '30'))
    min_days: int = int(os.getenv('MIN_HISTORY_DAYS', '7'))
    min_samples: int = int(os.getenv('MIN_HISTORY_SAMPLES', '7'))
    cooldown: int = int(os.getenv('COOLDOWN_HOURS', '24'))
    browser: bool = os.getenv('PLAYWRIGHT_ENABLED', 'false').lower() == 'true'
    sources_file: str = os.getenv('SOURCES_FILE', 'sources.json')
    market_enabled: bool = os.getenv('MARKET_ENABLED', 'true').lower() == 'true'
    min_market_sellers: int = int(os.getenv('MIN_MARKET_SELLERS', '3'))

    def validate(self):
        if self.interval < 900 or self.min_days < 2 or self.min_samples < 2:
            raise ValueError('Tarama >=900 saniye, geçmiş >=2 gün ve >=2 örnek olmalı')
        if not 0 < self.min_discount < 100 or self.max_price < 0 or self.min_reference < 0:
            raise ValueError('Geçersiz fiyat kriteri')
        if self.min_market_sellers < 3:
            raise ValueError('Piyasa kıyası için en az 3 bağımsız referans satıcı gerekli')
        if self.provider not in ('telegram', 'ntfy'):
            raise ValueError('Bilinmeyen bildirim kanalı')
        if self.provider == 'ntfy' and not self.dry_run:
            import re
            if not re.fullmatch(r'[A-Za-z0-9_-]{20,100}', self.ntfy_topic):
                raise ValueError('Geçerli ntfy kanalı gerekli')
        if not self.dry_run and self.provider == 'telegram' and not (self.token and self.chat_id):
            raise ValueError('Canlı bildirim için TELEGRAM_BOT_TOKEN ve CHAT_ID gerekli')
