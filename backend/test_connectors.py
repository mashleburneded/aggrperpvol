import asyncio
from datetime import datetime, timedelta, timezone
import os
import sys
from decimal import Decimal

# Adjust path to import app modules
# This assumes the script is run from `aggrperpvol/backend/` or `aggrperpvol/`
# If run from `aggrperpvol/backend/scripts/`, path needs to be `../app`
try:
    from app.services.exchange_connectors.base_connector import BaseExchangeConnector
    from app.services.exchange_connectors.woox_connector import WooXConnector
    from app.services.exchange_connectors.paradex_connector import ParadexConnector
    from app.models.api_key import PlatformEnum
    from app import schemas # For schemas.HistoricalKline, schemas.ExchangeVolumeInfo
except ImportError:
    # Simple path adjustment if run from the backend directory directly
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from app.services.exchange_connectors.base_connector import BaseExchangeConnector
    from app.services.exchange_connectors.woox_connector import WooXConnector
    from app.services.exchange_connectors.paradex_connector import ParadexConnector
    from app.models.api_key import PlatformEnum
    from app import schemas


# --- Configuration for Testing ---
# IMPORTANT: Fill in your API keys/JWTs here for testing private endpoints.
# DO NOT COMMIT THIS FILE WITH REAL KEYS.
TEST_API_KEYS = {
    PlatformEnum.WOOX: {"api_key": "YOUR_WOOX_API_KEY", "api_secret": "YOUR_WOOX_API_SECRET"},
    PlatformEnum.PARADEX: {"jwt_token": "YOUR_PARADEX_JWT_TOKEN"} # Crucial for Paradex
}

# Symbols to test for each platform (adjust as needed for user data)
TEST_SYMBOLS = {
    PlatformEnum.WOOX: "PERP_BTC_USDT", # Example, ensure this is a market the test user traded
    PlatformEnum.PARADEX: "ETH-USD-PERP" # Example, ensure this is a market the test user traded
}

async def test_connector_historical_klines(connector: BaseExchangeConnector, symbol: str):
    print(f"\n--- Testing get_historical_klines (user's daily trade summaries) for {connector.get_platform_name().value} - {symbol} ---")
    
    end_dt = datetime.now(timezone.utc) - timedelta(days=1) # Yesterday
    start_dt = end_dt - timedelta(days=7) # Fetch 7 days of data

    start_time_ms = int(start_dt.timestamp() * 1000)
    end_time_ms = int(end_dt.timestamp() * 1000)
    interval = connector.get_daily_interval_string() # Use the connector's daily interval

    auth_params = TEST_API_KEYS.get(connector.get_platform_name())

    try:
        # Pass auth_params to the connector method
        klines = await connector.get_historical_klines(
            symbol=symbol,
            interval=interval,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            auth_params=auth_params # Pass the auth dictionary
        )
        
        if klines:
            print(f"Fetched {len(klines)} daily summaries. First 3:")
            for kline in klines[:3]:
                print(kline)
            print("Last 3:")
            for kline in klines[-3:]:
                print(kline)
            
            # Verify type if possible (assuming schemas.HistoricalKline or similar for daily summary)
            if all(isinstance(k, schemas.HistoricalKline) for k in klines):
                print("All summaries are of type schemas.HistoricalKline.")
            else:
                print("WARNING: Not all summaries are of type schemas.HistoricalKline.")
                print(f"Type of first summary: {type(klines[0]) if klines else 'N/A'}")

        else:
            print("No daily summaries fetched (likely no user trades in the period for this symbol).")
            
    except Exception as e:
        print(f"Error during get_historical_klines (user daily summaries) for {connector.get_platform_name().value}: {e}")
        import traceback
        traceback.print_exc()

async def test_connector_24h_volume(connector: BaseExchangeConnector, symbol_for_platform: str):
    # Note: get_latest_24h_volume in connectors is now designed to return platform total,
    # so the 'symbol_for_platform' is more for context here, not directly passed if method doesn't take it.
    print(f"\n--- Testing get_latest_24h_volume for {connector.get_platform_name().value} ---")
    
    auth_params = TEST_API_KEYS.get(connector.get_platform_name())

    try:
        # Pass auth_params to the connector method
        volume_info = await connector.get_latest_24h_volume(auth_params=auth_params)
        
        if volume_info:
            print(f"Platform: {volume_info.platform_name}")
            print(f"Symbol (represents platform total): {volume_info.symbol}")
            print(f"Volume 24h USD: {volume_info.volume_24h_usd}")
            print(f"Timestamp: {volume_info.timestamp}")
            if volume_info.error:
                print(f"Error reported: {volume_info.error}")
        else:
            print("No 24h volume info returned.")
            
    except Exception as e:
        print(f"Error during get_latest_24h_volume for {connector.get_platform_name().value}: {e}")
        import traceback
        traceback.print_exc()

async def main():
    # --- Select which connector to test ---
    # platform_to_test = PlatformEnum.WOOX
    platform_to_test = PlatformEnum.PARADEX # Default to Paradex for testing

    connector: Optional[BaseExchangeConnector] = None
    symbol = ""

    if platform_to_test == PlatformEnum.WOOX:
        connector = WooXConnector()
        symbol = TEST_SYMBOLS[PlatformEnum.WOOX]
    elif platform_to_test == PlatformEnum.PARADEX:
        connector = ParadexConnector()
        symbol = TEST_SYMBOLS[PlatformEnum.PARADEX]
    else:
        print(f"Connector for {platform_to_test.value} not implemented or selected in this script.")
        return

    if connector:
        # Test fetching user's historical daily trade summaries
        # Ensure you have valid API keys/JWT in TEST_API_KEYS.
        print(f"Ensure you have valid API credentials in TEST_API_KEYS for {platform_to_test.value}")
        print(f"and that the test user has traded the symbol '{symbol}' in the last 8 days.")
        await test_connector_historical_klines(connector, symbol)
        
        print("-" * 50)
        
        # Test fetching user's 24h personal volume
        await test_connector_24h_volume(connector, symbol) # symbol is for context here

if __name__ == "__main__":
    asyncio.run(main())
