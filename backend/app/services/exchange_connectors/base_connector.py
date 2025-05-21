from abc import ABC, abstractmethod
from datetime import date
from typing import List, Dict, Any, Optional
from decimal import Decimal
import httpx # Using httpx for async requests

from ....schemas import HistoricalVolumeRecord # Adjusted import path
from ....models.api_key import PlatformEnum # Adjusted import path

class BaseExchangeConnector(ABC):
    """
    Abstract Base Class for exchange connectors.
    Each connector will implement methods to fetch historical volume data.
    """
    # Default timeout for HTTP requests
    REQUEST_TIMEOUT = 30  # seconds

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, extra_auth_params: Optional[Dict[str, Any]] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.extra_auth_params = extra_auth_params # For things like wallet addresses, JWTs, etc.
        self.base_url = self.get_base_url()

    @abstractmethod
    def get_platform_name(self) -> PlatformEnum:
        """Returns the PlatformEnum member for this connector."""
        pass

    @abstractmethod
    def get_base_url(self) -> str:
        """Returns the base API URL for the exchange."""
        pass

    @abstractmethod
    async def get_historical_klines(
        self,
        symbol: str,
        interval: str, # e.g., "1d", "1h", "D" - specific to exchange
        start_time_ms: int,
        end_time_ms: int,
        limit: Optional[int] = None # Exchange-specific limit
    ) -> List[Dict[str, Any]]: # Raw kline data from exchange
        """
        Fetches historical kline/candlestick data from the exchange.
        This method should handle authentication, request formation, and basic error handling.
        It should return a list of kline data points as dictionaries.
        """
        pass

    @abstractmethod
    def _transform_kline_to_historical_volume_record(
        self,
        kline_data: Dict[str, Any],
        symbol: str, # The symbol we requested
        platform: PlatformEnum
    ) -> Optional[HistoricalVolumeRecord]:
        """
        Transforms a single kline data point (from get_historical_klines)
        into a HistoricalVolumeRecord schema.
        Returns None if the kline_data cannot be transformed (e.g., missing volume).
        """
        pass

    async def fetch_historical_daily_volume(
        self,
        symbol: str,
        start_date: date,
        end_date: date
    ) -> List[HistoricalVolumeRecord]:
        """
        Fetches and transforms historical daily volume data for a given symbol and date range.
        This method will typically call get_historical_klines with appropriate parameters
        for daily data and then transform the results.
        It should handle pagination if the exchange API requires it for long date ranges.
        """
        # Default implementation might involve converting dates to timestamps,
        # calling get_historical_klines with a daily interval, and then transforming.
        # Connectors might override this if they have a more direct way to get daily volume.
        
        all_records: List[HistoricalVolumeRecord] = []
        
        # Example: Convert start_date and end_date to milliseconds for get_historical_klines
        # This is a simplified loop; actual pagination logic will be more complex and exchange-specific.
        # For now, this assumes get_historical_klines can fetch the whole range or handles its own pagination.

        start_timestamp_ms = int(start_date.strftime("%s")) * 1000
        end_timestamp_ms = int(end_date.strftime("%s")) * 1000 # Or end of day

        # This is a placeholder for interval. Each exchange will have its own.
        # For daily, it might be "1D", "D", "1d", etc.
        daily_interval = self.get_daily_interval_string()


        # This is a simplified example. Real implementation needs robust pagination.
        # Some APIs return data oldest first, some newest first.
        # Some use cursor pagination, some use timestamp offsets.
        
        # For demonstration, let's assume a simple scenario where we fetch in one go (if possible)
        # or a very basic pagination. Proper pagination will be implemented in each connector.
        
        try:
            raw_klines = await self.get_historical_klines(
                symbol=symbol,
                interval=daily_interval,
                start_time_ms=start_timestamp_ms,
                end_time_ms=end_timestamp_ms,
                # limit might be per page, so loop might be needed
            )

            for kline_data in raw_klines:
                record = self._transform_kline_to_historical_volume_record(
                    kline_data=kline_data,
                    symbol=symbol, # Pass the original requested symbol
                    platform=self.get_platform_name()
                )
                if record:
                    # Ensure the date of the record is within the requested range
                    # (some APIs might return data slightly outside due to interval boundaries)
                    if start_date <= record.date <= end_date:
                        all_records.append(record)
            
            # Sort by date just in case the API doesn't guarantee it or pagination reverses order
            all_records.sort(key=lambda r: r.date)

        except httpx.HTTPStatusError as e:
            print(f"HTTP error fetching data for {symbol} on {self.get_platform_name()}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            print(f"Request error fetching data for {symbol} on {self.get_platform_name()}: {e}")
        except Exception as e:
            print(f"Generic error fetching data for {symbol} on {self.get_platform_name()}: {e}")
            
        return all_records

    @abstractmethod
    def get_daily_interval_string(self) -> str:
        """Returns the string representation for daily interval for this exchange."""
        pass

    @abstractmethod
    async def get_latest_24h_volume(self, symbol: str) -> Optional[schemas.ExchangeVolumeInfo]:
        """
        Fetches the latest 24h trading volume for a specific symbol.
        Returns an ExchangeVolumeInfo structure (or relevant parts) 
        or None if data is unavailable.
        The 'date' field in the returned record should represent the end date of the 24h period.
        """
        pass
