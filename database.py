from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from sqlalchemy import String, Numeric, DateTime, ForeignKey, JSON, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from engine import evaluate, market_deal

class Base(DeclarativeBase): pass

class Product(Base):
    __tablename__ = 'products'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(String(1000))
    seller: Mapped[str] = mapped_column(String(200))
    last_alerted_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    notification_sent_at: Mapped[datetime | None] = mapped_column(DateTime)

class Observation(Base):
    __tablename__ = 'observations'
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey('products.id'), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)

class Alert(Base):
    __tablename__ = 'alerts'
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey('products.id'), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default='pending', index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Database:
    def __init__(self, config):
        self.config = config
        Path('data').mkdir(exist_ok=True)
        self.engine = create_async_engine(config.database_url, pool_pre_ping=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def record(self, item, current_offers=()):
        now = datetime.utcnow()
        async with self.sessions.begin() as session:
            product = await session.get(Product, item['id'])
            if product is None:
                product = Product(id=item['id'], url=item['url'], title=item['title'], seller=item['seller'])
                session.add(product)
                await session.flush()
            rows = (await session.execute(select(Observation.observed_at, Observation.price).where(
                Observation.product_id == product.id,
                Observation.observed_at >= now - timedelta(days=self.config.history_days)
            ))).all()
            deal = evaluate(item['price'], rows, now, self.config)
            basis, peers = 'history', []
            if not deal:
                market = market_deal(item, current_offers, self.config)
                if market:
                    deal, peers, basis = market[:2], market[2], 'market'
            session.add(Observation(product_id=product.id, price=item['price'], observed_at=now))
            pending = await session.scalar(select(Alert.id).where(Alert.product_id == product.id, Alert.status == 'pending'))
            allowed = product.notification_sent_at is None or item['price'] < product.last_alerted_price or now - product.notification_sent_at >= timedelta(hours=self.config.cooldown)
            if deal and allowed and not pending:
                reference, discount = deal
                payload = {**item, 'price': str(item['price']), 'reference': str(reference), 'discount': str(discount), 'basis':basis, 'peers':peers}
                session.add(Alert(product_id=product.id, payload=payload))
                return True
        return False
