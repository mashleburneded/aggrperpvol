import httpx
from datetime import datetime, date, timezone
from typing import List, Dict, Any, Optional
from decimal import Decimal
import asyncio
import logging # Added logging

from .base_connector import BaseExchangeConnector
from .... import schemas # Import schemas directly
from ....models.api_key import PlatformEnum

logger = logging.getLogger(__name__) # Added logger

class ParadexConnector(BaseExchangeConnector):
    def get_platform_name(self) -> PlatformEnum:
        return PlatformEnum.PARADEX

    def get_base_url(self) -> str:
        return "https://api.prod.paradex.trade"

    def get_daily_interval_string(self) -> str:
        # This might not be directly applicable if we're summing trades,
        # but Paradex /v1/account/list-fills takes start_at and end_at in ms.
        return "1D" # Placeholder, actual aggregation will be daily.

    async def get_user_historical_fills(
        self,
        symbol: str,
        start_time_ms: int,
        end_time_ms: int,
        auth_params: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = 5000 # Max page_size for Paradex
    ) -> List[Dict[str, Any]]: # Return list of raw fill objects
        """
        Fetches historical fills for a specific symbol and time range from Paradex.
        Handles pagination.
        """
        all_fills: List[Dict[str, Any]] = []
        
        jwt_token = auth_params.get("jwt_token") if auth_params else None
        if not jwt_token:
            logger.error("ParadexConnector: JWT token not provided for /v1/account/list-fills.")
            return []

        headers = {"Authorization": f"Bearer {jwt_token}", "Accept": "application/json"}
        
        api_params: Dict[str, Any] = {
            "market": symbol,
            "start_at": start_time_ms,
            "end_at": end_time_ms,
            "page_size": limit or 5000 # Use provided limit or max
        }
        
        cursor: Optional[str] = None
        max_retries = 3
        retry_delay_seconds = 5

        async with httpx.AsyncClient(base_url=self.get_base_url(), headers=headers, timeout=self.REQUEST_TIMEOUT) as client:
            while True: # Loop for pagination
                current_retry = 0
                if cursor:
                    api_params["cursor"] = cursor
                
                while current_retry < max_retries:
                    try:
                        logger.info(f"Paradex: Attempt {current_retry + 1}/{max_retries} Fetching fills for symbol '{symbol}'. Params: {api_params}")
                        response = await client.get("/v1/account/list-fills", params=api_params)

                        if response.status_code == 429:
                            logger.warning(f"Paradex rate limit hit for {symbol}. Retrying in {retry_delay_seconds}s...")
                            await asyncio.sleep(retry_delay_seconds)
                            current_retry += 1
                            continue
                        
                        response.raise_for_status()
                        data = response.json()
                        
                        page_fills = data.get("results", [])
                        if isinstance(page_fills, list):
                            all_fills.extend(page_fills)
                        
                        cursor = data.get("next")
                        if not cursor: # No more pages
                            return all_fills 
                        
                        # Successfully fetched a page, break retry loop and continue pagination
                        break 

                    except httpx.HTTPStatusError as e_http:
                        logger.error(f"Paradex HTTP error for {symbol} (Attempt {current_retry + 1}): {e_http.response.status_code} - {e_http.response.text}")
                        if e_http.response.status_code in [500, 502, 503, 504] and current_retry < max_retries - 1:
                            await asyncio.sleep(retry_delay_seconds)
                            current_retry += 1
                        else:
                            return all_fills # Return what we have so far on critical error
                    except httpx.RequestError as e_req:
                        logger.error(f"Paradex Request error for {symbol} (Attempt {current_retry + 1}): {e_req}")
                        if current_retry < max_retries - 1:
                            await asyncio.sleep(retry_delay_seconds)
                            current_retry += 1
                        else:
                            return all_fills # Return what we have so far
                    except Exception as e_gen:
                        logger.error(f"Unexpected error fetching Paradex fills for {symbol} (Attempt {current_retry + 1}): {e_gen}", exc_info=True)
                        return all_fills # Return what we have so far
                
                if current_retry == max_retries: # Exhausted retries for this page
                    logger.error(f"Paradex: Max retries reached for page with cursor {api_params.get('cursor')}. Returning collected fills.")
                    return all_fills
        return all_fills # Should be unreachable if pagination loop breaks correctly

    async def get_historical_klines(
        self,
        symbol: str,
        interval: str, # Interval here is conceptual (daily), actual data is from fills
        start_time_ms: int,
        end_time_ms: int,
        auth_params: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None # Limit for page_size in get_user_historical_fills
    ) -> List[schemas.HistoricalKline]:
        
        raw_fills = await self.get_user_historical_fills(
            symbol=symbol,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            auth_params=auth_params,
            limit=limit 
        )

        if not raw_fills:
            return []

        daily_aggregated_data: Dict[date, Dict[str, Decimal]] = {}

        for fill in raw_fills:
            try:
                # Assuming fill structure based on typical exchange fill data
                # These field names are speculative and need to be confirmed from actual API response
                timestamp_ms = int(fill.get("created_at") or fill.get("timestamp")) # Prefer 'created_at' if available
                price_str = str(fill.get("price"))
                size_str = str(fill.get("size") or fill.get("quantity")) # 'size' or 'quantity'
                # market_symbol = fill.get("market") # To ensure it matches requested symbol

                # if market_symbol != symbol: # Should not happen if API filters by market
                #     continue

                dt_object = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
                current_date = dt_object.date()

                price = Decimal(price_str)
                size = Decimal(size_str)
                quote_volume = price * size # This is the USD equivalent volume for this trade

                if current_date not in daily_aggregated_data:
                    daily_aggregated_data[current_date] = {
                        "open": price, "high": price, "low": price, "close": price, 
                        "volume": Decimal("0.0") # This will be quote volume
                    }
                
                day_data = daily_aggregated_data[current_date]
                day_data["high"] = max(day_data["high"], price)
                day_data["low"] = min(day_data["low"], price)
                day_data["close"] = price # Last trade of the day will set this
                day_data["volume"] += quote_volume
            
            except Exception as e:
                logger.warning(f"Paradex: Error processing fill data for {symbol}: {fill}. Error: {e}", exc_info=True)
                continue
        
        transformed_klines: List[schemas.HistoricalKline] = []
        for record_date, data in sorted(daily_aggregated_data.items()):
            transformed_klines.append(schemas.HistoricalKline(
                timestamp=datetime(record_date.year, record_date.month, record_date.day, tzinfo=timezone.utc),
                open=data["open"],
                high=data["high"],
                low=data["low"],
                close=data["close"],
                volume=data["volume"] # This is quote volume (USD equivalent)
            ))
        
        return transformed_klines

    async def get_latest_24h_volume(self, auth_params: Optional[Dict[str, Any]] = None) -> Optional[schemas.ExchangeVolumeInfo]:
        """
        Calculates the total 24h personal trading volume by fetching recent fills.
        """
        now = datetime.now(timezone.utc)
        start_of_24h_period_ms = int((now - asyncio.timedelta(hours=24)).timestamp() * 1000)
        end_of_24h_period_ms = int(now.timestamp() * 1000)
        
        total_volume_usd_24h = Decimal("0.0")
        
        # We need to iterate over all markets the user might have traded on.
        # This requires knowing which markets to check. For simplicity, if the API
        # allows fetching fills without specifying a market (account-wide), that's better.
        # If not, we'd need a list of user's active/traded markets.
        # For now, let's assume we can fetch account-wide fills if `symbol` is omitted.
        # If `market` is mandatory for list-fills, this approach needs rethinking.
        # The docs say `market` is Optional for list-fills.

        logger.info(f"Paradex: Fetching account-wide fills for the last 24 hours to calculate volume.")
        
        # Fetch fills for all markets (by omitting 'market' param if API supports it)
        # If not, this logic needs to be adapted to iterate over known/relevant markets.
        # The current `get_user_historical_fills` requires a symbol.
        # We'll adapt by calling it for a placeholder "ALL_MARKETS" and let it handle.
        # This is a simplification; a real implementation might need to list markets first.
        
        # Let's assume for now we need to sum up volumes from individual market calls if account-wide is not feasible.
        # This part is complex without knowing all markets a user trades.
        # A simpler approach if /v1/markets/summary provides user-specific 24h volume:
        
        jwt_token = auth_params.get("jwt_token") if auth_params else None
        headers = {"Accept": "application/json"}
        if jwt_token:
            headers["Authorization"] = f"Bearer {jwt_token}"

        async with httpx.AsyncClient(base_url=self.get_base_url(), headers=headers, timeout=self.REQUEST_TIMEOUT) as client:
            try:
                logger.info(f"Paradex: Attempting to fetch /v1/markets/summary for 24h volume overview.")
                response = await client.get("/v1/markets/summary") # This is likely public market data
                response.raise_for_status()
                data = response.json()
                
                results = data.get("results", [])
                if not results or not isinstance(results, list):
                    logger.warning(f"Paradex: No market summary data from /v1/markets/summary. Response: {data}")
                    # Fallback to calculating from recent fills if summary is not user-specific or unavailable
                else:
                    # This is MARKET summary, not USER summary. We cannot use this for personal 24h volume.
                    # We MUST calculate from user's fills.
                    logger.info("Paradex: /v1/markets/summary provides market data, not user-specific 24h volume. Will calculate from fills.")
                    pass # Proceed to calculate from fills

            except Exception as e_summary:
                logger.warning(f"Paradex: Error fetching /v1/markets/summary, will proceed to calculate from fills: {e_summary}")

        # Calculate from user's fills (account-wide if possible, or iterate markets)
        # For now, this example won't iterate all markets due to complexity.
        # A real implementation would need a strategy for this (e.g., user specifies markets, or query all user positions/orders).
        # We'll demonstrate for a single, hypothetical "TOTAL" symbol if the API supported it,
        # or one would sum up volumes from calls to get_user_historical_fills for each relevant market.
        
        # This is a placeholder. A robust solution would fetch fills for all relevant markets.
        # For now, returning 0 as we cannot reliably get total 24h user volume without knowing all markets.
        logger.warning("Paradex: get_latest_24h_volume is a placeholder. A robust implementation needs to iterate user's traded markets or use an account-wide 24h volume endpoint if available.")
        
        # If an endpoint like /v1/account/summary existed that gave 24h user volume, it would be ideal.
        # Since it doesn't seem to, we'd have to:
        # 1. Get a list of all markets the user has traded/has positions in.
        # 2. For each market, call get_user_historical_fills for the last 24h.
        # 3. Sum the quote_volume from these fills.
        # This is too complex for this step without more info on how to get user's active markets.
        
        return schemas.ExchangeVolumeInfo(
            platform_name=self.get_platform_name().value,
            symbol="PARADEX_ACCOUNT_TOTAL", # Placeholder
            volume_24h_usd=0.0, # Placeholder - requires iterating all user markets
            timestamp=datetime.now(timezone.utc),
            error="Accurate 24h total user volume requires iterating all traded markets; not fully implemented."
        )
