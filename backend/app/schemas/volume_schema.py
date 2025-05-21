from pydantic import BaseModel
from datetime import date
from typing import List, Optional, Dict
from decimal import Decimal
from ..models.api_key import PlatformEnum

class HistoricalVolumeRecord(BaseModel):
    date: date
    platform: PlatformEnum
    symbol: str
    volume_base: Decimal
    volume_quote: Optional[Decimal] = None

    class Config:
        orm_mode = True
        # from_attributes = True # For Pydantic V2

class AggregatedHistoricalVolumePoint(BaseModel):
    date: date
    total_volume_quote: Decimal # Assuming aggregation in a common quote currency (e.g., USD)
    platform_contributions: Optional[Dict[PlatformEnum, Decimal]] = None # Optional breakdown

class HistoricalVolumeResponse(BaseModel):
    start_date: date
    end_date: date
    granularity: str # e.g., "daily", "weekly", "monthly"
    data: List[AggregatedHistoricalVolumePoint]
    # Could also include individual platform historical data if needed for charts
    # platform_data: Optional[Dict[PlatformEnum, List[HistoricalVolumeRecord]]] = None


class CurrentVolumeResponse(BaseModel):
    total_aggregated_volume_24h_quote: Decimal # Assuming USD
    last_updated: str # ISO format timestamp
    platform_contributions: Optional[Dict[PlatformEnum, Decimal]] = None

class PublicVolumeResponse(BaseModel):
    total_volume_24h: str # Formatted string, e.g., "$1.23T"
    # Or, if providing raw number for client-side formatting:
    # total_volume_24h_raw: Decimal
    last_updated_timestamp: int # Unix timestamp ms
