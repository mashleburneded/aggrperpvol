import httpx
import time
import hashlib
import hmac
from datetime import datetime, date, timezone, timedelta
from typing import List, Dict, Any, Optional
from decimal import Decimal
import asyncio

from .base_connector import BaseExchangeConnector
from .... import schemas # Import schemas directly
from ....models.api_key import PlatformEnum
from ....core.config import settings # For API keys if used directly by backend

class WooXConnector(BaseExchangeConnector):
    def get_platform_name(self) -> PlatformEnum:
        return PlatformEnum.WOOX

    def get_base_url(self, public: bool = False) -> str:
        if public:
            return "https://api-pub.woo.org" # For public data like historical klines (if ever needed)
        return "https://api.woox.io" # For private data like user trades

    def get_daily_interval_string(self) -> str:
        # Not directly used for fetching trades, but conceptual for aggregation
        return "1d"

    def _generate_signature_for_woox(self, timestamp_ms: str, query_params: Dict[str, Any], api_secret: str) -> str:
        """
        Generates HMAC SHA256 signature for WOO X API private GET requests.
        stringToSign = sorted_query_string + "|" + timestamp
        """
        sorted_query_string = "&".join([f"{k}={v}" for k, v in sorted(query_params.items())])
        string_to_sign = f"{sorted_query_string}|{timestamp_ms}"
        
        signature = hmac.new(
            api_secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    async def _fetch_trades_from_endpoint(
        self,
        endpoint_path: str,
        symbol: str,
        start_time_ms: int,
        end_time_ms: int,
        auth_params: Dict[str, Any],
        page_param_name: str, # "page" or "fromId"
        page_size_param_name: str, # "size" or "limit"
        initial_page_value: Any,
        page_size: int
    ) -> List[Dict[str, Any]]:
        all_trades_data: List[Dict[str, Any]] = []
        current_page_or_cursor = initial_page_value
        
        max_pages_safety = 200 # Safety break for pagination loops
        loop_count = 0
        max_retries = 3
        retry_delay_seconds = 5

        api_key = auth_params.get("api_key")
        api_secret = auth_params.get("api_secret")

        if not api_key or not api_secret:
            logging.error("WooXConnector: API key or secret not provided for private endpoint.")
            return []

        async with httpx.AsyncClient(base_url=self.get_base_url(public=False), timeout=self.REQUEST_TIMEOUT) as client:
            while loop_count < max_pages_safety:
                loop_count += 1
                current_retry = 0
                
                timestamp_ms_str = str(int(time.time() * 1000))
                query_params: Dict[str, Any] = {
                    "symbol": symbol,
                    "start_t": start_time_ms,
                    "end_t": end_time_ms,
                    page_param_name: current_page_or_cursor,
                    page_size_param_name: page_size,
                }
                # Remove None values, convert all to str for sorting/signing
                query_params_for_sign = {k: str(v) for k, v in query_params.items() if v is not None}


                signature = self._generate_signature_for_woox(timestamp_ms_str, query_params_for_sign, api_secret)
                
                headers = {
                    "x-api-key": api_key,
                    "x-api-signature": signature,
                    "x-api-timestamp": timestamp_ms_str,
                    "Content-Type": "application/json" 
                }

                # Use query_params_for_sign for the actual request as well, as they are stringified
                request_params = query_params_for_sign.copy() # Use a copy for the request

                while current_retry < max_retries:
                    try:
                        logging.info(f"WooX: Attempt {current_retry + 1}/{max_retries} Fetching {endpoint_path} for {symbol}. Params: {request_params}")
                        response = await client.get(endpoint_path, params=request_params, headers=headers)

                        if response.status_code == 429:
                            logging.warning(f"WooX rate limit hit for {symbol} at {endpoint_path}. Retrying in {retry_delay_seconds}s...")
                            await asyncio.sleep(retry_delay_seconds)
                            current_retry += 1
                            continue
                        
                        response.raise_for_status()
                        data = response.json()

                        if not data.get("success"):
                            api_msg = data.get('message', f'Unknown WooX API error at {endpoint_path}')
                            logging.error(f"WooX API error for {symbol} ({endpoint_path}): {api_msg}. Response: {data}")
                            return all_trades_data # Stop pagination on API error

                        trades_page: List[Dict[str, Any]] = data.get("rows", []) # V1 /client/trades and /client/hist_trades use "rows"

                        if not trades_page:
                            return all_trades_data # No more data

                        all_trades_data.extend(trades_page)
                        
                        if page_param_name == "page": # Page-based pagination for /v1/client/trades
                            meta = data.get("meta", {})
                            current_page_from_meta = meta.get("current_page", current_page_or_cursor)
                            total_pages = meta.get("total_page", current_page_from_meta) # Assume current is total if not present
                            if current_page_from_meta >= total_pages:
                                return all_trades_data
                            current_page_or_cursor += 1
                        elif page_param_name == "fromId": # Cursor-based for /v1/client/hist_trades
                            # WOO X hist_trades doesn't explicitly return a 'next_cursor'.
                            # We infer by checking if fewer records than limit were returned,
                            # or if the last trade's ID is the same as the current `fromId` (unlikely if new data).
                            # A common pattern is to use the ID of the last fetched item as the next `fromId`.
                            # However, WOO X docs say "If fromId is provided, the query will start after this trade_id."
                            # This means we need the *first* ID of the next set, or rely on page size.
                            # For simplicity, if len(trades_page) < page_size, assume end.
                            # More robust: if last trade timestamp > end_time_ms, or if no new unique IDs.
                            if len(trades_page) < page_size:
                                return all_trades_data
                            # For cursor, update fromId to the ID of the last trade fetched to get items *after* it.
                            # WOO X API: "If fromId is provided, the query will start after this trade_id."
                            # This means we need to use the ID of the *last* item in the current batch.
                            current_page_or_cursor = trades_page[-1]["id"]
                        
                        await asyncio.sleep(0.2) # WOO X private API rate limit is 5 req/sec
                        break # Success for this page/batch

                    except httpx.HTTPStatusError as e_http:
                        logging.error(f"WooX HTTP error for {symbol} ({endpoint_path}, Attempt {current_retry + 1}): {e_http.response.status_code} - {e_http.response.text}")
                        if e_http.response.status_code in [500, 502, 503, 504] and current_retry < max_retries - 1:
                            await asyncio.sleep(retry_delay_seconds)
                            current_retry += 1
                        else:
                            return all_trades_data 
                    except httpx.RequestError as e_req:
                        logging.error(f"WooX Request error for {symbol} ({endpoint_path}, Attempt {current_retry + 1}): {e_req}")
                        if current_retry < max_retries - 1:
                            await asyncio.sleep(retry_delay_seconds)
                            current_retry += 1
                        else:
                            return all_trades_data
                    except Exception as e_gen:
                        logging.error(f"Unexpected error fetching WooX trades for {symbol} ({endpoint_path}, Attempt {current_retry + 1}): {e_gen}", exc_info=True)
                        return all_trades_data
                
                if current_retry == max_retries:
                    logging.error(f"WooX: Max retries reached for {endpoint_path} page/cursor {current_page_or_cursor}. Returning collected trades.")
                    return all_trades_data
        return all_trades_data


    async def get_user_historical_trades(
        self,
        symbol: str, # WOO X format: SPOT_BTC_USDT, PERP_BTC_USDT
        start_time_ms: int,
        end_time_ms: int,
        auth_params: Optional[Dict[str, Any]] = None,
        limit_per_page: Optional[int] = 100 
    ) -> List[Dict[str, Any]]:
        
        if not auth_params:
            logging.error("WooXConnector: auth_params (API key & secret) are required for fetching user trades.")
            return []

        all_trades: List[Dict[str, Any]] = []
        
        # Define the 3-month boundary for WOO X trade history
        three_months_ago_ms = int((datetime.now(timezone.utc) - timedelta(days=90)).timestamp() * 1000)

        # Fetch recent trades (last 3 months) if the period overlaps
        if end_time_ms > three_months_ago_ms:
            recent_start_time_ms = max(start_time_ms, three_months_ago_ms)
            logging.info(f"WooX: Fetching recent trades for {symbol} from {datetime.fromtimestamp(recent_start_time_ms/1000)} to {datetime.fromtimestamp(end_time_ms/1000)}")
            recent_trades = await self._fetch_trades_from_endpoint(
                endpoint_path="/v1/client/trades",
                symbol=symbol,
                start_time_ms=recent_start_time_ms,
                end_time_ms=end_time_ms,
                auth_params=auth_params,
                page_param_name="page",
                page_size_param_name="size",
                initial_page_value=1,
                page_size=limit_per_page or 100
            )
            all_trades.extend(recent_trades)

        # Fetch archived trades (older than 3 months) if the period overlaps
        if start_time_ms < three_months_ago_ms:
            archived_end_time_ms = min(end_time_ms, three_months_ago_ms -1) # Ensure no overlap
            if start_time_ms <= archived_end_time_ms: # Check if there's still a valid range
                logging.info(f"WooX: Fetching archived trades for {symbol} from {datetime.fromtimestamp(start_time_ms/1000)} to {datetime.fromtimestamp(archived_end_time_ms/1000)}")
                # For hist_trades, fromId is a cursor. Initial call might not need it or use a very old known ID if available.
                # For simplicity, we'll start without fromId and rely on time window.
                # WOO X API: "start_t and end_t are required for /v1/client/hist_trades"
                archived_trades = await self._fetch_trades_from_endpoint(
                    endpoint_path="/v1/client/hist_trades",
                    symbol=symbol,
                    start_time_ms=start_time_ms,
                    end_time_ms=archived_end_time_ms,
                    auth_params=auth_params,
                    page_param_name="fromId", # This is a cursor, initial call might be tricky if no prior ID known.
                                              # The API might work with just time range for the first call.
                                              # If not, we might need to make an initial call to get a starting point or handle it.
                                              # For now, assuming it works with time range for the first call, or we start with None.
                    page_size_param_name="limit",
                    initial_page_value=None, # Initial call for cursor-based might not need fromId
                    page_size=limit_per_page or 100
                )
                all_trades.extend(archived_trades)
        
        # Deduplicate and sort if necessary, though fetching distinct periods should minimize duplicates.
        # Sorting by timestamp is good practice.
        unique_trades = {trade['id']: trade for trade in all_trades}
        sorted_trades = sorted(list(unique_trades.values()), key=lambda x: x['executed_timestamp'])
        
        return sorted_trades

    async def get_historical_klines(
        self,
        symbol: str, 
        interval: str, # Conceptual "1d"
        start_time_ms: int,
        end_time_ms: int,
        auth_params: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None # Page size for fetching trades
    ) -> List[schemas.HistoricalKline]:
        
        raw_trades = await self.get_user_historical_trades(
            symbol=symbol,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            auth_params=auth_params,
            limit_per_page=limit or 100 # Pass limit as page size for underlying trade fetch
        )

        if not raw_trades:
            return []

        daily_aggregated_data: Dict[date, Dict[str, Decimal]] = {}

        for trade in raw_trades:
            try:
                # WOO X trade fields: executed_timestamp, executed_price, executed_quantity, fee, fee_asset, side
                timestamp_ms = int(trade["executed_timestamp"])
                price = Decimal(str(trade["executed_price"]))
                quantity = Decimal(str(trade["executed_quantity"])) # This is base asset quantity
                
                # Volume for our schema is quote_volume (USD equivalent)
                quote_volume = price * quantity 

                dt_object = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
                current_date = dt_object.date()

                if not (date.fromtimestamp(start_time_ms / 1000) <= current_date <= date.fromtimestamp(end_time_ms / 1000)):
                    continue # Ensure trade is within the requested daily aggregation period

                if current_date not in daily_aggregated_data:
                    daily_aggregated_data[current_date] = {
                        "open": price, "high": price, "low": price, "close": price, 
                        "volume": Decimal("0.0") # Sum of quote volumes
                    }
                
                day_data = daily_aggregated_data[current_date]
                day_data["high"] = max(day_data["high"], price)
                day_data["low"] = min(day_data["low"], price)
                day_data["close"] = price # Last trade of the day will set this
                day_data["volume"] += quote_volume
            
            except (KeyError, ValueError, TypeError) as e:
                logging.warning(f"WooX: Error processing trade data for {symbol}: {trade}. Error: {e}", exc_info=True)
                continue
        
        transformed_klines: List[schemas.HistoricalKline] = []
        for record_date, data in sorted(daily_aggregated_data.items()):
            transformed_klines.append(schemas.HistoricalKline(
                timestamp=datetime(record_date.year, record_date.month, record_date.day, tzinfo=timezone.utc),
                open=data["open"],
                high=data["high"],
                low=data["low"],
                close=data["close"],
                volume=data["volume"] 
            ))
        
        return transformed_klines

    async def get_latest_24h_volume(self, auth_params: Optional[Dict[str, Any]] = None) -> Optional[schemas.ExchangeVolumeInfo]:
        now = datetime.now(timezone.utc)
        start_of_24h_period_ms = int((now - timedelta(hours=24)).timestamp() * 1000)
        end_of_24h_period_ms = int(now.timestamp() * 1000)
        
        total_volume_usd_24h = Decimal("0.0")

        if not auth_params:
            logging.error("WooXConnector: auth_params (API key & secret) are required for fetching 24h user volume.")
            return schemas.ExchangeVolumeInfo(
                platform_name=self.get_platform_name().value,
                volume_24h_usd=0.0,
                timestamp=now,
                error="API credentials not provided."
            )

        # This is a simplification. In a real scenario, you'd need to know which symbols
        # the user trades to fetch their volume accurately. Or, if WOO X has an account-wide
        # trade history endpoint (not apparent from docs), that would be better.
        # For now, we'll assume we need to be told which symbols to check or have a predefined list.
        # As a placeholder, this function won't iterate all possible symbols.
        # It should ideally fetch trades for *all* user's traded symbols in the last 24h.
        
        # Example: If we knew the user trades PERP_BTC_USDT and PERP_ETH_USDT
        # symbols_to_check = ["PERP_BTC_USDT", "PERP_ETH_USDT"] 
        # For now, we'll make it a placeholder that would need actual symbols.
        
        logging.warning("WooX: get_latest_24h_volume is a placeholder. A robust implementation needs to iterate user's traded markets or use an account-wide 24h volume endpoint if available.")
        # To make this functional, one would loop through relevant user symbols:
        # for symbol in user_traded_symbols_on_woox:
        #     trades_24h = await self.get_user_historical_trades(
        #         symbol=symbol,
        #         start_time_ms=start_of_24h_period_ms,
        #         end_time_ms=end_of_24h_period_ms,
        #         auth_params=auth_params,
        #         limit_per_page=100 # Adjust as needed
        #     )
        #     for trade in trades_24h:
        #         try:
        #             price = Decimal(str(trade["executed_price"]))
        #             quantity = Decimal(str(trade["executed_quantity"]))
        #             total_volume_usd_24h += price * quantity
        #         except Exception: # Handle potential errors in trade data
        #             pass
        
        return schemas.ExchangeVolumeInfo(
            platform_name=self.get_platform_name().value,
            symbol="WOOX_ACCOUNT_TOTAL", # Placeholder
            volume_24h_usd=float(total_volume_usd_24h), # Placeholder
            timestamp=now,
            error="Accurate 24h total user volume requires iterating all traded markets; not fully implemented for WOOX." if total_volume_usd_24h == Decimal("0.0") else None
        )
