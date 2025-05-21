import httpx
import time
import hashlib
import hmac
from datetime import datetime, date, timezone, timedelta
from typing import List, Dict, Any, Optional
from decimal import Decimal
import asyncio # For potential sleep during pagination

from .base_connector import BaseExchangeConnector
from .... import schemas # Import schemas directly
from ....models.api_key import PlatformEnum # Adjusted import path
# from ....core.config import settings # Not using direct settings for API keys here

class BybitConnector(BaseExchangeConnector):
    def get_platform_name(self) -> PlatformEnum:
        return PlatformEnum.BYBIT

    def get_base_url(self) -> str:
        return "https://api.bybit.com"

    def get_daily_interval_string(self) -> str:
        return "D"

    # Bybit V5 public endpoints for kline do not require authentication
    # If private endpoints were needed, signature generation would be here.

    async def get_historical_klines(
        self,
        symbol: str,
        interval: str, # e.g., "D" for daily
        start_time_ms: int,
        end_time_ms: int,
        limit: Optional[int] = 1000 # Max limit for Bybit kline is 1000
    ) -> List[List[str]]: # Bybit returns klines as list of lists of strings
        
        all_klines_data: List[List[str]] = []
        current_fetch_start_ms = start_time_ms

        # Determine category (linear/inverse) based on symbol
        # This is a simplified check; a more robust mapping might be needed.
        category = "linear"
        if symbol.endswith("USD") and not symbol.endswith("USDT") and not symbol.endswith("USDC"):
            category = "inverse"
        
        max_loops = 100 # Safety break for pagination
        loop_count = 0
        max_retries = 3
        retry_delay_seconds = 5

        while current_fetch_start_ms <= end_time_ms and loop_count < max_loops:
            loop_count += 1
            current_retry = 0
            params = {
                "category": category,
                "symbol": symbol,
                "interval": interval,
                "start": str(current_fetch_start_ms),
                "end": str(end_time_ms), # Keep original end_time_ms for each request
                "limit": str(limit or 1000),
            }

            async with httpx.AsyncClient(base_url=self.get_base_url(), timeout=self.REQUEST_TIMEOUT) as client:
                try:
                    print(f"Bybit: Fetching {symbol} from {datetime.fromtimestamp(current_fetch_start_ms/1000)} with params {params}")
                    while current_retry < max_retries:
                        try:
                            print(f"Bybit: Attempt {current_retry + 1}/{max_retries} Fetching {symbol} from {datetime.fromtimestamp(current_fetch_start_ms/1000)} with params {params}")
                            response = await client.get("/v5/market/kline", params=params)
                            
                            if response.status_code == 429: # Rate limit
                                print(f"Bybit rate limit hit for {symbol}. Retrying in {retry_delay_seconds}s...")
                                await asyncio.sleep(retry_delay_seconds)
                                current_retry += 1
                                continue # Retry the request

                            response.raise_for_status() # Raise HTTPStatusError for 4xx/5xx responses not 429
                            data = response.json()

                            if data.get("retCode") != 0:
                                ret_msg = data.get('retMsg', 'Unknown Bybit API error')
                                print(f"Bybit API error for {symbol}: {ret_msg} (Code: {data.get('retCode')})")
                                # Specific error codes might warrant a break or different handling
                                # e.g. if retCode indicates invalid symbol, no point retrying.
                                if data.get("retCode") == 10001: # Example: Parameter error
                                    print(f"Parameter error for {symbol} on Bybit. Stopping for this symbol.")
                                    loop_count = max_loops # Break outer while loop
                                break # Break retry loop for this page

                            klines_page: List[List[str]] = data.get("result", {}).get("list", [])
                            
                            if not klines_page:
                                loop_count = max_loops # No more data, break outer while loop
                                break # Break retry loop

                            all_klines_data.extend(klines_page)
                            
                            last_kline_in_page_start_ms = int(klines_page[-1][0])
                            
                            if last_kline_in_page_start_ms >= end_time_ms:
                                loop_count = max_loops # Fetched up to the end
                                break 
                            
                            if len(klines_page) < (limit or 1000):
                                loop_count = max_loops # Reached end of available data
                                break

                            interval_duration_ms = self._interval_to_ms(interval)
                            current_fetch_start_ms = last_kline_in_page_start_ms + interval_duration_ms
                            
                            await asyncio.sleep(0.2) # Increased sleep to 200ms
                            break # Success, break retry loop for this page

                        except httpx.HTTPStatusError as e_http:
                            print(f"Bybit HTTP error for {symbol} (Attempt {current_retry + 1}): {e_http.response.status_code} - {e_http.response.text}")
                            if e_http.response.status_code in [500, 502, 503, 504] and current_retry < max_retries -1: # Server errors
                                print(f"Retrying in {retry_delay_seconds}s...")
                                await asyncio.sleep(retry_delay_seconds)
                                current_retry += 1
                            else: # Non-retryable HTTP error or max retries reached
                                loop_count = max_loops # Break outer while loop
                                break # Break retry loop
                        except httpx.RequestError as e_req: # Network errors, timeouts
                            print(f"Bybit Request error for {symbol} (Attempt {current_retry + 1}): {e_req}")
                            if current_retry < max_retries -1:
                                print(f"Retrying in {retry_delay_seconds}s...")
                                await asyncio.sleep(retry_delay_seconds)
                                current_retry += 1
                            else:
                                loop_count = max_loops # Break outer while loop
                                break # Break retry loop
                        except Exception as e_gen:
                            print(f"Unexpected error fetching Bybit klines for {symbol} (Attempt {current_retry + 1}): {e_gen}")
                            loop_count = max_loops # Break outer while loop
                            break # Break retry loop
                    if loop_count == max_loops : # If any inner break set loop_count to max_loops
                        break # Break from the outer while current_fetch_start_ms loop

        # Deduplicate and sort
        if all_klines_data:
            unique_klines_map = {kline_item[0]: kline_item for kline_item in all_klines_data} # Use timestamp as key for uniqueness
            all_klines_data = sorted(list(unique_klines_map.values()), key=lambda x: int(x[0]))
        
        # Transform to schemas.HistoricalKline
        transformed_klines: List[schemas.HistoricalKline] = []
        for kline_item in all_klines_data:
            try:
                # [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
                transformed_kline = schemas.HistoricalKline(
                    timestamp=datetime.fromtimestamp(int(kline_item[0]) / 1000, tz=timezone.utc),
                    open=Decimal(kline_item[1]),
                    high=Decimal(kline_item[2]),
                    low=Decimal(kline_item[3]),
                    close=Decimal(kline_item[4]),
                    # Use turnover (quote asset volume) for 'volume' field in HistoricalKline
                    # as this is typically what's used for USD normalization.
                    volume=Decimal(kline_item[6]) 
                )
                transformed_klines.append(transformed_kline)
            except (IndexError, ValueError, TypeError) as e:
                print(f"Bybit: Error transforming kline data for {symbol}: {kline_item}, Error: {e}")
        
        return transformed_klines

    # This method is not directly used by the new BaseExchangeConnector structure for get_historical_klines
    # def _transform_kline_to_historical_volume_record( 
    #     self,
    #     kline_data: List[str], 
    #     symbol: str, 
    #     platform: PlatformEnum
    # ) -> Optional[HistoricalVolumeRecord]:
    #     try:
    #         # kline_data: [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
    #         timestamp_ms = int(kline_data[0])
    #         record_date = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).date()
            
    #         volume_base_str = kline_data[5]
    #         volume_quote_str = kline_data[6] # Turnover

    #         if volume_base_str is None or volume_base_str == "" or Decimal(volume_base_str) == Decimal(0):
    #             return None

    #         return HistoricalVolumeRecord( # This schema is not defined in the provided schemas
    #             date=record_date,
    #             platform=platform,
    #             symbol=symbol, 
    #             volume_base=Decimal(volume_base_str),
    #             volume_quote=Decimal(volume_quote_str) if volume_quote_str else Decimal("0.0")
    #         )
    #     except (IndexError, ValueError, TypeError) as e:
    #         print(f"Error transforming Bybit kline data for {symbol}: {kline_data}, Error: {e}")
    #         return None

    def _interval_to_ms(self, interval: str) -> int:
        if interval == "D": return 24 * 60 * 60 * 1000
        if interval == "W": return 7 * 24 * 60 * 60 * 1000
        if interval == "M": return 30 * 24 * 60 * 60 * 1000 # Approximate for month
        
        if interval.isnumeric(): # For minute intervals like "1", "5", "60"
            return int(interval) * 60 * 1000
        
        # Fallback for other potential interval strings if needed, e.g., "1h", "4h"
        # This part would need more robust parsing if various intervals are used.
        # For "D", the numeric check won't pass.
        print(f"Warning: Unknown interval '{interval}' for _interval_to_ms, defaulting to 1 day.")
        return 24 * 60 * 60 * 1000 # Default to 1 day

    async def get_latest_24h_volume(self, auth_params: Optional[Dict[str, Any]] = None) -> Optional[schemas.ExchangeVolumeInfo]:
        # This method should aggregate volume for all relevant symbols for Bybit
        # For simplicity, let's assume we are interested in total USDT perp volume.
        # A more robust solution would get symbols from platform_symbol_map in AggregationService.
        # Here, we'll fetch all linear tickers and sum their turnover.
        
        category = "linear" # For USDT and USDC perps
        total_turnover_usd = Decimal("0.0")
        
        # Fetch all tickers for the linear category
        # Bybit's /v5/market/tickers without a symbol returns all tickers for the category
        params = {"category": category}
        async with httpx.AsyncClient(base_url=self.get_base_url(), timeout=self.REQUEST_TIMEOUT) as client:
            try:
                print(f"Bybit: Fetching all {category} tickers for 24h volume.")
                response = await client.get("/v5/market/tickers", params=params)
                response.raise_for_status()
                data = response.json()

                if data.get("retCode") != 0:
                    print(f"Bybit API error for {category} tickers: {data.get('retMsg')}")
                    return schemas.ExchangeVolumeInfo(
                        platform_name=self.get_platform_name().value,
                        volume_24h_usd=0.0,
                        timestamp=datetime.now(timezone.utc),
                        error=f"API Error: {data.get('retMsg')}"
                    )
                
                result_list = data.get("result", {}).get("list", [])
                if not result_list:
                    print(f"No ticker data found for {category} category on Bybit.")
                    return schemas.ExchangeVolumeInfo(
                        platform_name=self.get_platform_name().value,
                        volume_24h_usd=0.0,
                        timestamp=datetime.now(timezone.utc),
                        error="No ticker data found"
                    )
                
                for ticker_data in result_list:
                    # We are interested in USDT or USDC pairs for linear
                    symbol = ticker_data.get("symbol", "")
                    if "USDT" in symbol or "USDC" in symbol: # Filter for stablecoin pairs
                        turnover_str = ticker_data.get("turnover24h")
                        if turnover_str:
                            try:
                                total_turnover_usd += Decimal(turnover_str)
                            except Exception as e_dec:
                                print(f"Bybit: Error converting turnover {turnover_str} to Decimal for {symbol}: {e_dec}")
                
                if total_turnover_usd == Decimal("0.0") and not result_list: # Check if list was empty vs all turnovers were zero
                     return schemas.ExchangeVolumeInfo(
                        platform_name=self.get_platform_name().value,
                        volume_24h_usd=0.0,
                        timestamp=datetime.now(timezone.utc),
                        error="No relevant USDT/USDC ticker data processed."
                    )


                return schemas.ExchangeVolumeInfo(
                    platform_name=self.get_platform_name().value,
                    # symbol field in ExchangeVolumeInfo is for individual symbol, not applicable here for aggregated platform volume
                    # However, the schema requires it. We can leave it as a general identifier.
                    symbol=f"{category.upper()}_TOTAL", 
                    volume_24h_usd=float(total_turnover_usd), # Schema expects float
                    timestamp=datetime.now(timezone.utc)
                )

            except httpx.HTTPStatusError as e:
                print(f"Bybit HTTP error for {category} tickers: {e.response.status_code} - {e.response.text}")
                return schemas.ExchangeVolumeInfo(
                    platform_name=self.get_platform_name().value,
                    volume_24h_usd=0.0,
                    timestamp=datetime.now(timezone.utc),
                    error=f"HTTP Error: {e.response.status_code}"
                )
            except Exception as e:
                print(f"Unexpected error fetching Bybit 24h volume for {category}: {e}")
                return schemas.ExchangeVolumeInfo(
                    platform_name=self.get_platform_name().value,
                    volume_24h_usd=0.0,
                    timestamp=datetime.now(timezone.utc),
                    error=f"Unexpected error: {str(e)}"
                )
