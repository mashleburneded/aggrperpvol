from sqlalchemy import Column, Integer, String, Date, Numeric, Enum as SAEnum, Index
from ..core.database import Base
from .api_key import PlatformEnum # Re-use PlatformEnum

class HistoricalDailyVolume(Base):
    __tablename__ = "historical_daily_volumes"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(SAEnum(PlatformEnum), nullable=False)
    symbol = Column(String, index=True, nullable=False) # e.g., BTC-USD-PERP, BTCUSDT
    date = Column(Date, index=True, nullable=False)
    
    # Volume in terms of the base asset (e.g., BTC amount for BTC/USD pair)
    volume_base = Column(Numeric(precision=30, scale=10), nullable=False)
    
    # Volume in terms of the quote asset (e.g., USD amount for BTC/USD pair)
    # This is often referred to as "turnover" or "quote volume"
    # Storing this helps in direct aggregation if all quote currencies are the same (e.g., USD)
    # or can be used with price data for normalization if quote currencies differ.
    volume_quote = Column(Numeric(precision=30, scale=10), nullable=True)

    # Optional: If we want to store the average price for that day's volume
    # average_price = Column(Numeric(precision=20, scale=8), nullable=True)

    __table_args__ = (
        Index('idx_platform_symbol_date', 'platform', 'symbol', 'date', unique=True),
    )

    def __repr__(self):
        return f"<HistoricalDailyVolume(platform='{self.platform.value}', symbol='{self.symbol}', date='{self.date}', volume_base={self.volume_base}, volume_quote={self.volume_quote})>"
