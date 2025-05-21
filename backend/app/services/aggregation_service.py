import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.config import settings
from app.models.api_key import APIKey
from app.models.historical_volume import HistoricalVolume
from app.schemas import volume_schema, api_key_schema
from app.crud import crud_historical_volume, crud_api_key
from app.services.exchange_connectors import (
    WooXConnector,
    ParadexConnector,
    BaseExchangeConnector,
)
from app.core.security import fernet_decrypt
from app.core.cache import get_cache, set_cache
import httpx # For making HTTP requests to CoinGecko

logger = logging.getLogger(__name__)

# CoinGecko API base URL
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"
# Simple cache for token IDs to avoid repeated lookups if we need to map symbols to CoinGecko IDs
COINGECKO_TOKEN_ID_CACHE: Dict[str, Optional[str]] = {}
# Cache for prices to reduce API calls
PRICE_CACHE: Dict[str, Dict[str, Any]] = {} # Key: coingecko_id, Value: {"price": float, "timestamp": datetime}
PRICE_CACHE_TTL_SECONDS = 5 * 60  # Cache prices for 5 minutes

class AggregationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.platform_symbol_map: Dict[str, List[str]] = {
            # "bybit": ["BTCUSDT", "ETHUSDT"], # Example symbols
            "woox": ["PERP_BTC_USDT", "PERP_ETH_USDT"],
            # "hyperliquid": ["BTC", "ETH"],
            "paradex": ["BTC-USD-PERP", "ETH-USD-PERP"], # Paradex might use different symbol formats
        }
        self.connectors: Dict[str, BaseExchangeConnector] = {
            # "bybit": BybitConnector(),
            "woox": WooXConnector(),
            # "hyperliquid": HyperliquidConnector(),
            "paradex": ParadexConnector(),
        }

    async def _get_active_api_key_for_platform(self, platform_name: str) -> Optional[api_key_schema.APIKeyDecrypted]:
        api_key_record = await crud_api_key.get_api_key_by_platform(self.db, platform_name=platform_name)
        if api_key_record and api_key_record.is_active:
            try:
                decrypted_key = fernet_decrypt(api_key_record.encrypted_api_key)
                decrypted_secret = fernet_decrypt(api_key_record.encrypted_api_secret)
                # Paradex might use a JWT or different auth, adjust as needed
                decrypted_jwt = fernet_decrypt(api_key_record.encrypted_jwt_token) if api_key_record.encrypted_jwt_token else None
                
                return api_key_schema.APIKeyDecrypted(
                    id=api_key_record.id,
                    platform_name=api_key_record.platform_name,
                    api_key=decrypted_key,
                    api_secret=decrypted_secret,
                    jwt_token=decrypted_jwt, 
                    user_id=api_key_record.user_id,
                    is_active=api_key_record.is_active,
                    created_at=api_key_record.created_at,
                    updated_at=api_key_record.updated_at
                )
            except Exception as e:
                logger.error(f"Failed to decrypt API key for {platform_name}: {e}")
                return None
        return None

    async def _get_coingecko_id(self, token_symbol: str) -> Optional[str]:
        """
        Maps a common token symbol (e.g., BTC, ETH) to CoinGecko's specific ID.
        Uses a simple in-memory cache. In a production system, this list might be
        pre-populated or fetched and cached more robustly.
        """
        upper_symbol = token_symbol.upper()
        if upper_symbol in COINGECKO_TOKEN_ID_CACHE:
            return COINGECKO_TOKEN_ID_CACHE[upper_symbol]

        # Basic mapping, extend as needed
        mapping = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "USDT": "tether",
            "USDC": "usd-coin",
            # Add other common symbols
        }
        coingecko_id = mapping.get(upper_symbol)
        
        if not coingecko_id:
            # Fallback: try to search if not in basic map (can be slow)
            # This is a simplified example; a real implementation might query /coins/list
            # and cache it, then search that local cache.
            # For now, we'll stick to the basic map for performance.
            logger.warning(f"No direct CoinGecko ID mapping for symbol: {token_symbol}. Price will default to 1.0 if not a stablecoin.")
            COINGECKO_TOKEN_ID_CACHE[upper_symbol] = None # Cache miss
            return None
        
        COINGECKO_TOKEN_ID_CACHE[upper_symbol] = coingecko_id
        return coingecko_id

    async def _get_usd_price(self, token_symbol: str, timestamp: datetime) -> float:
        """
        Fetches the USD price for a given token symbol around a specific timestamp.
        Uses CoinGecko API and includes caching.
        Note: CoinGecko's free /simple/price endpoint gives current price, not historical.
        For historical prices, /coins/{id}/history?date={dd-mm-yyyy} would be needed,
        which is more complex. For simplicity, this example will fetch current price
        and assume it's a reasonable proxy if the timestamp is recent, or use a fallback.
        A more robust solution would use a paid API or a dedicated price oracle service.
        """
        upper_symbol = token_symbol.upper()
        if "USD" in upper_symbol: # USDT, USDC, USD
            return 1.0

        coingecko_id = await self._get_coingecko_id(upper_symbol)
        if not coingecko_id:
            logger.warning(f"Cannot fetch price for {token_symbol} (unknown CoinGecko ID). Defaulting to 1.0.")
            return 1.0

        # Check cache first
        cached_entry = PRICE_CACHE.get(coingecko_id)
        if cached_entry and (datetime.now(timezone.utc) - cached_entry["timestamp"]) < timedelta(seconds=PRICE_CACHE_TTL_SECONDS):
            logger.info(f"Using cached price for {token_symbol} ({coingecko_id}): {cached_entry['price']}")
            return cached_entry["price"]

        try:
            async with httpx.AsyncClient() as client:
                # Using /simple/price for current price.
                # For historical, would need /coins/{id}/history?date=...&localization=false
                # Example for current price:
                response = await client.get(f"{COINGECKO_API_URL}/simple/price", params={"ids": coingecko_id, "vs_currencies": "usd"})
                response.raise_for_status() # Raise an exception for HTTP errors
                data = response.json()
                
                price = data.get(coingecko_id, {}).get("usd")
                if price is not None:
                    logger.info(f"Fetched price for {token_symbol} ({coingecko_id}) from CoinGecko: {price}")
                    PRICE_CACHE[coingecko_id] = {"price": float(price), "timestamp": datetime.now(timezone.utc)}
                    return float(price)
                else:
                    logger.warning(f"USD price not found for {coingecko_id} in CoinGecko response. Data: {data}")
                    return 1.0 # Default if price not found
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching price for {coingecko_id} from CoinGecko: {e.response.status_code} - {e.response.text}")
            # Fallback to cached price if available, even if stale
            if cached_entry: return cached_entry["price"]
            return 1.0 # Default on error
        except Exception as e:
            logger.error(f"Error fetching price for {coingecko_id} from CoinGecko: {e}")
            if cached_entry: return cached_entry["price"]
            return 1.0 # Default on error

    async def _normalize_historical_volume_record(
        self, 
        raw_volume_record: volume_schema.HistoricalKline,
        platform_name: str,
        symbol: str
    ) -> Optional[volume_schema.HistoricalVolumeRecordCreate]:
        try:
            # Assuming raw_volume_record.volume is in quote asset if not USD, or base asset if quote is USD
            # This logic needs to be robust based on how each exchange reports volume
            
            quote_asset = ""
            # The raw_volume_record.volume from connectors is now already quote_volume_usd
            # derived from fills (price * size).
            # The `open`, `high`, `low`, `close` fields in HistoricalKline are also derived from fill prices.
            
            # Determine quote asset from symbol for record keeping
            quote_asset = "USD" # Default assumption for perps
            if "USDT" in symbol: quote_asset = "USDT"
            elif "USDC" in symbol: quote_asset = "USDC"
            # Paradex symbols like "BTC-USD-PERP" imply USD. WOO X "PERP_BTC_USDT" implies USDT.

            return volume_schema.HistoricalVolumeRecordCreate(
                platform_name=platform_name,
                symbol=symbol,
                timestamp=raw_volume_record.timestamp,
                volume_usd=raw_volume_record.volume, # This is already quote_volume_usd
                raw_volume=raw_volume_record.volume, # Store the same as it's already processed
                raw_quote_asset=quote_asset
            )
        except Exception as e:
            logger.error(f"Error creating HistoricalVolumeRecordCreate for {symbol} on {platform_name}: {e}", exc_info=True)
            return None

    async def fetch_and_store_historical_data_for_platform(
        self, 
        platform_name: str, 
        start_date: datetime, 
        end_date: datetime
    ) -> Dict[str, Any]:
        connector = self.connectors.get(platform_name)
        if not connector:
            logger.error(f"No connector found for platform: {platform_name}")
            return {"status": "error", "platform": platform_name, "message": "Connector not found"}

        api_key_details = await self._get_active_api_key_for_platform(platform_name)
        
        # Both WOO X and Paradex require auth for fetching user fills/trades
        if not api_key_details:
            logger.warning(f"Active API key required for {platform_name} historical data, but not found or inactive.")
            return {"status": "error", "platform": platform_name, "message": f"API key required for {platform_name}"}

        auth_params = {
            "api_key": api_key_details.api_key, 
            "api_secret": api_key_details.api_secret, 
            "jwt_token": api_key_details.jwt_token
        }
        
        symbols = self.platform_symbol_map.get(platform_name, [])
        if not symbols:
            logger.warning(f"No symbols defined for platform: {platform_name}")
            return {"status": "success", "platform": platform_name, "message": "No symbols to fetch"}

        total_records_fetched = 0
        total_records_stored = 0
        errors = []

        for symbol in symbols:
            try:
                logger.info(f"Fetching historical data for {symbol} on {platform_name} from {start_date} to {end_date}")
                # Connectors' get_historical_klines now processes fills into daily kline-like structures
                daily_kline_summaries = await connector.get_historical_klines(
                    symbol=symbol,
                    interval=connector.get_daily_interval_string(), # Conceptual interval
                    start_time_ms=int(start_date.timestamp() * 1000),
                    end_time_ms=int(end_date.timestamp() * 1000),
                    auth_params=auth_params
                )
                
                if daily_kline_summaries:
                    total_records_fetched += len(daily_kline_summaries) # Each summary is one day's record
                    records_to_store_db: List[HistoricalVolume] = []
                    for daily_summary in daily_kline_summaries:
                        # The volume in daily_summary is already quote_volume_usd
                        db_record = HistoricalVolume(
                            platform_name=platform_name,
                            symbol=symbol,
                            timestamp=daily_summary.timestamp,
                            open_price=daily_summary.open,
                            high_price=daily_summary.high,
                            low_price=daily_summary.low,
                            close_price=daily_summary.close,
                            volume_usd=daily_summary.volume, # This is already USD equivalent
                            raw_volume=daily_summary.volume, # Store the same as it's processed
                            raw_quote_asset=symbol.split('_')[-1] if platform_name == "woox" else symbol.split('-')[1] # Infer quote
                        )
                        records_to_store_db.append(db_record)
                    
                    if records_to_store_db:
                        # Using a more direct batch insert if your CRUD supports it, or adapt
                        await self.db.execute(HistoricalVolume.__table__.insert(), [r.to_dict() for r in records_to_store_db])
                        await self.db.commit()
                        total_records_stored += len(records_to_store_db)
                        logger.info(f"Stored {len(records_to_store_db)} daily aggregated records for {symbol} on {platform_name}")
                else:
                    logger.info(f"No daily kline summaries generated for {symbol} on {platform_name} (likely no trades).")

            except Exception as e:
                logger.error(f"Error fetching/storing data for {symbol} on {platform_name}: {e}", exc_info=True)
                errors.append(f"Error for {symbol}: {str(e)}")
        
        if errors:
             return {"status": "partial_success", "platform": platform_name, "fetched": total_records_fetched, "stored": total_records_stored, "errors": errors}
        return {"status": "success", "platform": platform_name, "fetched": total_records_fetched, "stored": total_records_stored}

    async def fetch_and_store_historical_data_for_all_active_platforms(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        if end_date is None:
            end_date = datetime.now(timezone.utc)
        if start_date is None:
            start_date = end_date - timedelta(days=settings.HISTORICAL_DATA_FETCH_DAYS)
        
        active_platforms = [
            platform for platform, connector in self.connectors.items()
        ] # In future, could filter by active API keys if all require auth

        tasks = []
        for platform_name in active_platforms:
            tasks.append(
                self.fetch_and_store_historical_data_for_platform(
                    platform_name, start_date, end_date
                )
            )
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        processed_results = []
        for i, result in enumerate(results):
            platform_name = active_platforms[i]
            if isinstance(result, Exception):
                logger.error(f"Unhandled exception fetching data for {platform_name}: {result}", exc_info=result)
                processed_results.append({"status": "error", "platform": platform_name, "message": str(result)})
            else:
                processed_results.append(result)
        return processed_results

    async def get_historical_aggregated_volume(
        self, start_date: datetime, end_date: datetime
    ) -> List[volume_schema.AggregatedVolumeDataPoint]:
        
        cache_key = f"historical_aggregated_volume_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}"
        cached_data = await get_cache(cache_key)
        if cached_data:
            try:
                # Assuming cached_data is a list of dicts that can be parsed into AggregatedVolumeDataPoint
                return [volume_schema.AggregatedVolumeDataPoint(**item) for item in cached_data]
            except Exception as e:
                logger.warning(f"Failed to parse cached historical aggregated volume: {e}. Fetching fresh data.")

        records = await crud_historical_volume.get_historical_volume_records_in_range(
            self.db, start_date, end_date
        )
        
        # Aggregate by day
        daily_aggregated_volume: Dict[datetime.date, float] = {}
        for record in records:
            record_date = record.timestamp.date()
            daily_aggregated_volume[record_date] = daily_aggregated_volume.get(record_date, 0.0) + record.volume_usd
            
        result = [
            volume_schema.AggregatedVolumeDataPoint(timestamp=datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc), aggregated_volume_usd=vol)
            for day, vol in sorted(daily_aggregated_volume.items())
        ]

        # Cache the result (convert Pydantic models to dicts for JSON serialization)
        await set_cache(cache_key, [item.model_dump() for item in result], expire=settings.CACHE_EXPIRATION_HISTORICAL)
        return result

    async def get_current_aggregated_volume(self) -> volume_schema.CurrentAggregatedVolume:
        cache_key = "current_aggregated_volume"
        cached_data = await get_cache(cache_key)
        if cached_data:
            try:
                return volume_schema.CurrentAggregatedVolume(**cached_data)
            except Exception as e:
                logger.warning(f"Failed to parse cached current aggregated volume: {e}. Fetching fresh data.")

        total_volume_usd = 0.0
        individual_platform_volumes: List[volume_schema.ExchangeVolumeInfo] = []
        
        active_platforms_with_keys = await crud_api_key.get_all_active_api_keys(self.db)
        platform_names_with_active_keys = {key.platform_name for key in active_platforms_with_keys}

        # Fetch for all defined connectors, use API keys if available and active
        connector_tasks = []
        platforms_for_tasks = []

        for platform_name, connector in self.connectors.items():
            api_key_details: Optional[api_key_schema.APIKeyDecrypted] = None
            if platform_name in platform_names_with_active_keys:
                 api_key_details = await self._get_active_api_key_for_platform(platform_name)
            
            auth_params = {}
            if api_key_details:
                 auth_params = {"api_key": api_key_details.api_key, "api_secret": api_key_details.api_secret, "jwt_token": api_key_details.jwt_token}

            # Collect all symbols for the platform
            platform_symbols = self.platform_symbol_map.get(platform_name, [])
            if not platform_symbols:
                logger.info(f"No symbols defined for {platform_name} for current volume.")
                continue
            
            platforms_for_tasks.append(platform_name)
            # Assuming get_latest_24h_volume can sum up volumes for all its relevant symbols
            # Or, it might need to be called per symbol if the API doesn't provide a total
            # For now, let's assume it returns total 24h volume for the platform
            connector_tasks.append(connector.get_latest_24h_volume(auth_params=auth_params))


        results = await asyncio.gather(*connector_tasks, return_exceptions=True)

        for i, result in enumerate(results):
            platform_name = platforms_for_tasks[i]
            if isinstance(result, Exception):
                logger.error(f"Error fetching 24h volume for {platform_name}: {result}", exc_info=result)
                individual_platform_volumes.append(
                    volume_schema.ExchangeVolumeInfo(platform_name=platform_name, volume_24h_usd=0.0, error=str(result))
                )
            elif result is not None:
                total_volume_usd += result.volume_24h_usd
                individual_platform_volumes.append(result)
            else: # result is None, no error explicitly raised but no data
                 individual_platform_volumes.append(
                    volume_schema.ExchangeVolumeInfo(platform_name=platform_name, volume_24h_usd=0.0, error="No data returned")
                )
        
        aggregated_data = volume_schema.CurrentAggregatedVolume(
            total_volume_24h_usd=total_volume_usd,
            last_updated=datetime.now(timezone.utc),
            individual_platforms=individual_platform_volumes
        )
        
        await set_cache(cache_key, aggregated_data.model_dump(), expire=settings.CACHE_EXPIRATION_CURRENT)
        return aggregated_data

    async def get_current_volume_for_platform(self, platform_name: str) -> Optional[volume_schema.ExchangeVolumeInfo]:
        connector = self.connectors.get(platform_name)
        if not connector:
            logger.error(f"No connector for platform: {platform_name}")
            return volume_schema.ExchangeVolumeInfo(platform_name=platform_name, volume_24h_usd=0.0, error="Connector not found")

        api_key_details = await self._get_active_api_key_for_platform(platform_name)
        auth_params = {}
        if api_key_details:
            auth_params = {"api_key": api_key_details.api_key, "api_secret": api_key_details.api_secret, "jwt_token": api_key_details.jwt_token}
        
        try:
            # This assumes get_latest_24h_volume sums up all relevant symbols for the platform
            # If it needs a symbol, this design needs adjustment or the connector needs to handle it.
            platform_volume_info = await connector.get_latest_24h_volume(auth_params=auth_params)
            if platform_volume_info:
                return platform_volume_info
            else:
                return volume_schema.ExchangeVolumeInfo(platform_name=platform_name, volume_24h_usd=0.0, error="No data returned by connector")
        except Exception as e:
            logger.error(f"Error fetching 24h volume for {platform_name}: {e}", exc_info=True)
            return volume_schema.ExchangeVolumeInfo(platform_name=platform_name, volume_24h_usd=0.0, error=str(e))
