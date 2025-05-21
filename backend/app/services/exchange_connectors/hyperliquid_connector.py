import httpx
from datetime import datetime, date, timezone
from typing import List, Dict, Any, Optional
from decimal import Decimal
import asyncio

from .base_connector import BaseExchangeConnector
from .... import schemas # Import schemas directly
from ....models.api_key import PlatformEnum
# from ....core.config import settings # API keys likely passed via constructor from DB

class HyperliquidConnector(BaseExchangeConnector):
    def get_platform_name(self) -> PlatformEnum:
        return PlatformEnum.HYPERLIQUID

    def get_base_url(self) -> str:
        # Hyperliquid's mainnet API endpoint
        return "https://api.hyperliquid.xyz"

    def get_daily_interval_string(self) -> str:
        # Hyperliquid uses intervals like "1m", "5m", "15m", "30m", "1h", "4h", "12h", "1d"
        # The SDK uses "1d" for daily candles.
        # However, the raw API might expect something like "D" or "1D".
        # Based on the SDK's `candles_snapshot` method, it takes an interval string.
        # Let's assume "1d" is a common representation or can be mapped.
        # The SDK's `info.py` uses `interval` directly in the request.
        # The example response shows "i": "1m". So "1d" is probably correct.
        return "1d" 

    async def get_historical_klines(
        self,
        symbol: str, # e.g., "BTC", "ETH" - SDK maps this to coin
        interval: str, # e.g., "1d"
        start_time_ms: int,
        end_time_ms: int,
        limit: Optional[int] = None # Limit not explicitly in SDK's candles_snapshot, implies full range or internal limit
    ) -> List[Dict[str, Any]]: # Hyperliquid returns klines as list of dicts
        
        all_klines_data: List[Dict[str, Any]] = []
        
        # Hyperliquid's `candles_snapshot` takes startTime and endTime.
        # It's unclear from the SDK if it paginates or has a max range.
        # We'll assume for now it can fetch a reasonable range (e.g., a few months to a year).
        # If it has a smaller limit, pagination logic would be needed here,
        # potentially by splitting the date range into smaller chunks.

        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": symbol, # The SDK maps common names like "BTC"
                "interval": interval,
                "startTime": start_time_ms,
                "endTime": end_time_ms,
            },
        }

        max_retries = 3
        retry_delay_seconds = 5
        current_retry = 0

        async with httpx.AsyncClient(base_url=self.get_base_url(), timeout=self.REQUEST_TIMEOUT) as client:
            while current_retry < max_retries:
                try:
                    print(f"Hyperliquid: Attempt {current_retry + 1}/{max_retries} Fetching {symbol} from {datetime.fromtimestamp(start_time_ms/1000)} to {datetime.fromtimestamp(end_time_ms/1000)}")
                    response = await client.post("/info", json=payload)
                    
                    # Hyperliquid might not use 429 for rate limits in the same way,
                    # but good to have a placeholder if observed.
                    if response.status_code == 429: 
                        print(f"Hyperliquid rate limit hit for {symbol}. Retrying in {retry_delay_seconds}s...")
                        await asyncio.sleep(retry_delay_seconds)
                        current_retry += 1
                        continue

                    response.raise_for_status()
                    # The response is directly a list of candle objects
                    klines_page: List[Dict[str, Any]] = response.json() 
                    
                    if not klines_page:
                        # This might mean no data for the range, or an issue.
                        # If it's a valid empty response, we should not retry.
                        print(f"Hyperliquid: No kline data returned for {symbol} in the range.")
                        return [] # No data, successful empty response

                    all_klines_data.extend(klines_page)
                    break # Success, exit retry loop
                    
                except httpx.HTTPStatusError as e_http:
                    print(f"Hyperliquid HTTP error for {symbol} (Attempt {current_retry + 1}): {e_http.response.status_code} - {e_http.response.text}")
                    if e_http.response.status_code in [500, 502, 503, 504] and current_retry < max_retries - 1: # Server errors
                        print(f"Retrying in {retry_delay_seconds}s...")
                        await asyncio.sleep(retry_delay_seconds)
                        current_retry += 1
                    else: # Non-retryable HTTP error or max retries reached
                        return [] # Return empty on persistent error
                except httpx.RequestError as e_req: # Network errors, timeouts
                    print(f"Hyperliquid Request error for {symbol} (Attempt {current_retry + 1}): {e_req}")
                    if current_retry < max_retries - 1:
                        print(f"Retrying in {retry_delay_seconds}s...")
                        await asyncio.sleep(retry_delay_seconds)
                        current_retry += 1
                    else:
                        return [] # Return empty on persistent error
                except Exception as e_gen:
                    print(f"Unexpected error fetching Hyperliquid klines for {symbol} (Attempt {current_retry + 1}): {e_gen}")
                    return [] # Return empty on other errors
        
        # Sort by timestamp ('t' field, which is start time of candle)
        all_klines_data.sort(key=lambda x: int(x["t"]))
        
        transformed_klines: List[schemas.HistoricalKline] = []
        for kline_item in all_klines_data:
            try:
                # kline_data: {"T": int, "c": str, "h": str, "i": str, "l": str, 
                #              "n": int, "o": str, "s": str, "t": int, "v": str}
                # 't' is start time of candle in ms. 'v' is base asset volume.
                # Calculate quote volume: v * ( (o+c)/2 )
                base_volume = Decimal(kline_item["v"])
                open_price = Decimal(kline_item["o"])
                close_price = Decimal(kline_item["c"])
                avg_price = (open_price + close_price) / 2
                quote_volume = base_volume * avg_price

                transformed_kline = schemas.HistoricalKline(
                    timestamp=datetime.fromtimestamp(int(kline_item["t"]) / 1000, tz=timezone.utc),
                    open=open_price,
                    high=Decimal(kline_item["h"]),
                    low=Decimal(kline_item["l"]),
                    close=close_price,
                    volume=quote_volume 
                )
                transformed_klines.append(transformed_kline)
            except (KeyError, ValueError, TypeError) as e:
                print(f"Hyperliquid: Error transforming kline data for {symbol}: {kline_item}, Error: {e}")
        
        return transformed_klines

    # _transform_kline_to_historical_volume_record is removed as transformation is now inline

    async def get_latest_24h_volume(self, auth_params: Optional[Dict[str, Any]] = None) -> Optional[schemas.ExchangeVolumeInfo]:
        payload = {"type": "metaAndAssetCtxs"}
        total_volume_usd = Decimal("0.0")
        
        # In a real scenario, we'd get relevant symbols from AggregationService.platform_symbol_map["hyperliquid"]
        # For now, let's assume we sum all available assets' dayNtlVlm.
        # This might not be perfectly accurate if some assets are not USD-quoted perps,
        # but dayNtlVlm is usually in USD for Hyperliquid.

        async with httpx.AsyncClient(base_url=self.get_base_url(), timeout=self.REQUEST_TIMEOUT) as client:
            try:
                print(f"Hyperliquid: Fetching metaAndAssetCtxs for 24h volume.")
                response = await client.post("/info", json=payload)
                response.raise_for_status()
                data = response.json() 
                
                if not isinstance(data, list) or len(data) < 2:
                    error_msg = "Unexpected response structure from Hyperliquid metaAndAssetCtxs"
                    print(error_msg)
                    return schemas.ExchangeVolumeInfo(
                        platform_name=self.get_platform_name().value,
                        volume_24h_usd=0.0, timestamp=datetime.now(timezone.utc), error=error_msg)

                # meta_universe = data[0].get("universe", []) # Contains names like "BTC", "ETH"
                asset_contexts = data[1] # This is a list of context objects

                if not asset_contexts:
                    error_msg = "No asset contexts found in Hyperliquid response."
                    print(error_msg)
                    return schemas.ExchangeVolumeInfo(
                        platform_name=self.get_platform_name().value,
                        volume_24h_usd=0.0, timestamp=datetime.now(timezone.utc), error=error_msg)

                for asset_ctx in asset_contexts:
                    # "dayNtlVlm": float string (This is 24h Notional Volume in USD)
                    volume_quote_str = asset_ctx.get("dayNtlVlm")
                    if volume_quote_str:
                        try:
                            total_volume_usd += Decimal(volume_quote_str)
                        except Exception as e_dec:
                             # meta_universe could be used here to get asset name for logging if indices match
                            print(f"Hyperliquid: Error converting dayNtlVlm {volume_quote_str} to Decimal: {e_dec}")
                
                return schemas.ExchangeVolumeInfo(
                    platform_name=self.get_platform_name().value,
                    symbol="HYPERLIQUID_TOTAL", 
                    volume_24h_usd=float(total_volume_usd),
                    timestamp=datetime.now(timezone.utc)
                )

            except httpx.HTTPStatusError as e:
                error_msg = f"Hyperliquid HTTP error for metaAndAssetCtxs: {e.response.status_code} - {e.response.text}"
                print(error_msg)
                return schemas.ExchangeVolumeInfo(
                    platform_name=self.get_platform_name().value,
                    volume_24h_usd=0.0, timestamp=datetime.now(timezone.utc), error=f"HTTP Error: {e.response.status_code}")
            except Exception as e:
                error_msg = f"Unexpected error fetching Hyperliquid 24h volume: {e}"
                print(error_msg)
                return schemas.ExchangeVolumeInfo(
                    platform_name=self.get_platform_name().value,
                    volume_24h_usd=0.0, timestamp=datetime.now(timezone.utc), error=f"Unexpected error: {str(e)}")
