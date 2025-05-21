import asyncio
import json
import logging
from datetime import date, datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession # Changed from sqlalchemy.orm import Session

# Assuming an async version of get_db will be provided or created
# from ..core.database import get_db 
from ..core.database import get_async_db # Placeholder for async session
from ..core.cache import get_cache, set_cache
from ..services.aggregation_service import AggregationService
from ..schemas import volume_schema # Using specific schemas from volume_schema

logger = logging.getLogger(__name__)
router = APIRouter()

# Cache constants (can be moved to config if preferred)
CACHE_KEY_CURRENT_AGGREGATED_VOLUME = "current_aggregated_volume"
CACHE_KEY_HISTORICAL_AGGREGATED_VOLUME_PREFIX = "historical_aggregated_volume"
CACHE_EXPIRY_SECONDS = 5 * 60  # 5 minutes

@router.post(
    "/historical/fetch-all",
    summary="Trigger historical data fetching for all platforms",
    response_model=List[Dict[str, Any]] # Generic response for now
)
async def trigger_fetch_historical_data_all_platforms(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD). Defaults to N days ago based on settings."),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD). Defaults to today."),
    db: AsyncSession = Depends(get_async_db)
):
    agg_service = AggregationService(db)
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc) if start_date else None
    end_dt = datetime.combine(end_date, datetime.min.time(), tzinfo=timezone.utc) if end_date else None
    
    results = await agg_service.fetch_and_store_historical_data_for_all_active_platforms(
        start_date=start_dt, 
        end_date=end_dt
    )
    return results

@router.post(
    "/historical/fetch-platform/{platform_name}",
    summary="Trigger historical data fetching for a specific platform",
    response_model=Dict[str, Any] # Generic response
)
async def trigger_fetch_historical_data_single_platform(
    platform_name: str,
    start_date: date = Query(..., description="Start date for historical data (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date for historical data (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_async_db)
):
    if platform_name not in AggregationService(db).connectors: # Check if platform is valid
        raise HTTPException(status_code=404, detail=f"Platform '{platform_name}' not supported.")
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="Start date cannot be after end date.")

    agg_service = AggregationService(db)
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.min.time(), tzinfo=timezone.utc)

    result = await agg_service.fetch_and_store_historical_data_for_platform(
        platform_name=platform_name,
        start_date=start_dt,
        end_date=end_dt
    )
    return result

@router.get("/historical", response_model=volume_schema.HistoricalVolumeResponse)
async def get_historical_aggregated_volume(
    start_date: date = Query(..., description="Start date for historical data (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date for historical data (YYYY-MM-DD)"),
    granularity: str = Query("daily", description="Granularity of data (daily is default/only for now)"),
    db: AsyncSession = Depends(get_async_db)
):
    if granularity != "daily":
        raise HTTPException(status_code=400, detail="Only 'daily' granularity is currently supported.")
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="Start date cannot be after end date.")

    agg_service = AggregationService(db)
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc) # Ensure end_date is inclusive

    # AggregationService.get_historical_aggregated_volume returns List[volume_schema.AggregatedVolumeDataPoint]
    # volume_schema.AggregatedVolumeDataPoint has: timestamp: datetime, aggregated_volume_usd: float
    # volume_schema.HistoricalVolumeResponse expects data: List[volume_schema.AggregatedHistoricalVolume]
    # volume_schema.AggregatedHistoricalVolume has: timestamp: date, total_volume_usd: Decimal
    
    service_data = await agg_service.get_historical_aggregated_volume(start_date=start_dt, end_date=end_dt)
    
    response_data_points: List[volume_schema.AggregatedHistoricalVolume] = []
    for point in service_data:
        response_data_points.append(
            volume_schema.AggregatedHistoricalVolume(
                timestamp=point.timestamp.date(), # Convert datetime to date
                total_volume_usd=Decimal(str(point.aggregated_volume_usd)) # Convert float to Decimal
            )
        )
    
    return volume_schema.HistoricalVolumeResponse(
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        data=response_data_points
    )

@router.get("/current", response_model=volume_schema.CurrentAggregatedVolume)
async def get_current_aggregated_volume_endpoint(db: AsyncSession = Depends(get_async_db)):
    agg_service = AggregationService(db)
    # The service method get_current_aggregated_volume now handles caching internally.
    current_volume_data = await agg_service.get_current_aggregated_volume()
    return current_volume_data

@router.get("/current/{platform_name}", response_model=Optional[volume_schema.ExchangeVolumeInfo])
async def get_current_volume_for_platform_endpoint(
    platform_name: str, 
    db: AsyncSession = Depends(get_async_db)
):
    agg_service = AggregationService(db)
    if platform_name not in agg_service.connectors:
        raise HTTPException(status_code=404, detail=f"Platform '{platform_name}' not supported.")
    
    platform_volume_info = await agg_service.get_current_volume_for_platform(platform_name)
    if platform_volume_info is None or (platform_volume_info.error and not platform_volume_info.volume_24h_usd): # Check if error and no volume
        # Return 200 with error message in body as per ExchangeVolumeInfo schema
        return platform_volume_info 
    return platform_volume_info


@router.get("/public/latest-volume", response_model=volume_schema.PublicVolumeResponse)
async def get_public_latest_volume(db: AsyncSession = Depends(get_async_db)):
    # This endpoint might be better served by the cached current aggregated volume
    agg_service = AggregationService(db)
    current_volume_data = await agg_service.get_current_aggregated_volume()
    
    total_volume_raw = Decimal(str(current_volume_data.total_volume_24h_usd))

    formatted_volume = f"${total_volume_raw / Decimal('1_000_000_000_000'):.2f}T"
    if total_volume_raw < Decimal('1_000_000_000_000'):
        if total_volume_raw < Decimal('1_000_000_000'):
            if total_volume_raw < Decimal('1_000_000'):
                 formatted_volume = f"${total_volume_raw / Decimal('1_000'):.2f}K"
            else:
                formatted_volume = f"${total_volume_raw / Decimal('1_000_000'):.2f}M"
        else:
            formatted_volume = f"${total_volume_raw / Decimal('1_000_000_000'):.2f}B"

    return volume_schema.PublicVolumeResponse(
        total_volume_24h=formatted_volume,
        last_updated_timestamp=int(current_volume_data.last_updated.timestamp() * 1000)
    )

@router.websocket("/ws/live-volume")
async def websocket_live_volume(websocket: WebSocket, db: AsyncSession = Depends(get_async_db)):
    await websocket.accept()
    logger.info("WebSocket client connected for live volume.")
    agg_service = AggregationService(db) # Create service instance once
    try:
        while True:
            # AggregationService's get_current_aggregated_volume handles caching.
            current_volume_data: volume_schema.CurrentAggregatedVolume = await agg_service.get_current_aggregated_volume()
            await websocket.send_json(current_volume_data.model_dump())
            await asyncio.sleep(5)  # Send update every 5 seconds
    except WebSocketDisconnect:
        logger.info("Client disconnected from live volume WebSocket.")
    except Exception as e:
        logger.error(f"Error in live volume WebSocket: {e}", exc_info=True)
        try:
            await websocket.send_json({"error": f"WebSocket error: {str(e)}"})
        except Exception: # If sending error also fails
            pass
    finally:
        logger.info("WebSocket connection closing.")
        # FastAPI handles closing the WebSocket connection on exit or unhandled exception.
