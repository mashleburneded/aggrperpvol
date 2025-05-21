from sqlalchemy.orm import Session
from sqlalchemy import func, Date as SQLDate # Import Date for casting
from datetime import date
from typing import List, Optional
from decimal import Decimal

from .. import models, schemas
from ..models.api_key import PlatformEnum # Re-use PlatformEnum

def create_historical_volume_record(db: Session, volume_data: schemas.HistoricalVolumeRecord):
    db_record = models.HistoricalDailyVolume(
        platform=volume_data.platform,
        symbol=volume_data.symbol,
        date=volume_data.date,
        volume_base=volume_data.volume_base,
        volume_quote=volume_data.volume_quote
    )
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    return db_record

def get_historical_volumes_by_platform_and_symbol(
    db: Session, 
    platform: PlatformEnum, 
    symbol: str, 
    start_date: date, 
    end_date: date, 
    skip: int = 0, 
    limit: int = 1000 # Allow fetching more for charting
):
    return (
        db.query(models.HistoricalDailyVolume)
        .filter(
            models.HistoricalDailyVolume.platform == platform,
            models.HistoricalDailyVolume.symbol == symbol,
            models.HistoricalDailyVolume.date >= start_date,
            models.HistoricalDailyVolume.date <= end_date,
        )
        .order_by(models.HistoricalDailyVolume.date)
        .offset(skip)
        .limit(limit)
        .all()
    )

def get_aggregated_daily_volume_for_all_platforms(
    db: Session, 
    target_date: date
) -> Optional[Decimal]:
    """
    Aggregates the quote_volume for a specific date across all platforms and symbols.
    Assumes volume_quote is in a common currency (e.g., USD).
    """
    total_volume_query = (
        db.query(func.sum(models.HistoricalDailyVolume.volume_quote))
        .filter(models.HistoricalDailyVolume.date == target_date)
    )
    total_volume = total_volume_query.scalar()
    return total_volume if total_volume is not None else Decimal("0.0")


def get_aggregated_historical_volume_range(
    db: Session,
    start_date: date,
    end_date: date,
    # platforms: Optional[List[PlatformEnum]] = None, # Future: filter by specific platforms
    # symbols: Optional[List[str]] = None # Future: filter by specific symbols
) -> List[schemas.AggregatedHistoricalVolumePoint]:
    """
    Aggregates quote_volume across all platforms and symbols for each day in the date range.
    """
    query = (
        db.query(
            models.HistoricalDailyVolume.date,
            func.sum(models.HistoricalDailyVolume.volume_quote).label("total_daily_volume_quote")
        )
        .filter(
            models.HistoricalDailyVolume.date >= start_date,
            models.HistoricalDailyVolume.date <= end_date,
        )
        # if platforms:
        #     query = query.filter(models.HistoricalDailyVolume.platform.in_(platforms))
        # if symbols:
        #     query = query.filter(models.HistoricalDailyVolume.symbol.in_(symbols))
        .group_by(models.HistoricalDailyVolume.date)
        .order_by(models.HistoricalDailyVolume.date)
    )
    
    results = query.all()
    
    aggregated_data = [
        schemas.AggregatedHistoricalVolumePoint(
            date=row.date,
            total_volume_quote=row.total_daily_volume_quote if row.total_daily_volume_quote is not None else Decimal("0.0")
        ) for row in results
    ]
    return aggregated_data

def bulk_insert_historical_volumes(db: Session, volume_records: List[schemas.HistoricalVolumeRecord]):
    """
    Efficiently inserts multiple historical volume records.
    Skips records if a unique constraint (platform, symbol, date) is violated.
    This requires PostgreSQL for ON CONFLICT DO NOTHING. For other DBs, check existence first or handle exceptions.
    """
    # For PostgreSQL:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    if not volume_records:
        return

    insert_stmt = pg_insert(models.HistoricalDailyVolume).values([
        {
            "platform": record.platform.value, # Ensure enum value is passed
            "symbol": record.symbol,
            "date": record.date,
            "volume_base": record.volume_base,
            "volume_quote": record.volume_quote,
        }
        for record in volume_records
    ])
    
    # ON CONFLICT DO NOTHING for the unique index ('idx_platform_symbol_date')
    # The index name must match exactly what's defined in the model.
    do_nothing_stmt = insert_stmt.on_conflict_do_nothing(
        index_elements=['platform', 'symbol', 'date'] # Specify columns of the unique constraint
    )
    
    db.execute(do_nothing_stmt)
    db.commit()

    # Note: For other databases or if not using PostgreSQL specific features,
    # you might need to check for existence before inserting each record
    # or catch integrity errors, which is less efficient for bulk operations.
