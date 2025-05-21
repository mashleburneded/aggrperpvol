# Active Context: Personal Aggregated Perpetual Volume Dashboard

## Current Work Focus
- **Project Scope Refinement:** Focusing the project on tracking **the user's personal trading volume** from WOO X and Paradex.
- **Memory Bank Revision:** Updating all core Memory Bank files (`projectbrief.md`, `productContext.md`, `systemPatterns.md`, `techContext.md`, this `activeContext.md`, and `progress.md`) to reflect this scope change.
- **API Endpoint Research (WOO X, Paradex):** The immediate next technical step will be to research the correct private API endpoints for WOO X and Paradex to fetch user-specific trade history or account volume summaries.

## Recent Changes (before pivot discovery)
- **Exchange Connectors:** Were previously (mis)configured to fetch public market data (klines, tickers). This code will need significant overhaul.
- **Aggregation Service:** Was designed to aggregate market data. This will also need overhaul to aggregate personal volume data.
- **Frontend:** UI elements for API key management and data display were implemented based on the market data assumption. Some UI elements might be reusable, but data handling logic will change.
- **Testing Script (`test_connectors.py`):** Was created to test market data fetching; will need to be adapted for testing user data endpoints.

## API Documentation Review Findings (Summarized - *Needs Re-evaluation for User Data*)
- **Previous research focused on public market data endpoints. This needs to be redone for user-specific data.**
- **WOO X:** Will need to find endpoints like `/v1/orders` (filled), `/v1/client/trades`, or account-specific volume summaries. Requires API key authentication.
- **Paradex:** The `/v1/account/history` endpoint with `type="volume"` is confirmed user-specific. Further investigation needed for market filtering and data granularity. JWT authentication is critical.

## Next Steps (Post Memory Bank Correction)
1.  **Update `progress.md`** to reflect the project scope change and current state of technical progress.
2.  **API Endpoint Research (High Priority - WOO X, Paradex):** For WOO X and Paradex, identify and document the correct private API endpoints for fetching:
    *   User's historical trade execution data (with price, quantity, symbol, timestamp, fees).
    *   User's 24-hour personal trading volume summary (if available directly, otherwise it will be calculated from recent trades).
    *   For Paradex, specifically investigate filtering and granularity of `GET /v1/account/history`. Also note the existence of `GET /account/transactions` as a potential alternative to `GET /v1/account/list-fills` if needed, though `list-fills` appears more suitable for detailed trade data.
3.  Revise Exchange Connectors (WOO X, Paradex):
    *   Rewrite `get_historical_klines` (likely rename to `get_historical_user_volume` or similar) in WOO X and Paradex connectors to use the newly identified user data endpoints. This will involve handling authentication for every call and parsing potentially very different response structures.
    *   Rewrite `get_latest_24h_volume` in WOO X and Paradex connectors to calculate the user's personal 24h volume from their recent trades or a specific summary endpoint.
4.  **Revise Data Models & Schemas:**
    *   Adjust `models/historical_volume.py` and `schemas/volume_schema.py` if the structure of "personal historical volume" (e.g., daily summary of user's trades) differs from market kline data.
5.  **Revise `AggregationService`:**
    *   Update logic to process and aggregate data from the revised connectors (user trade data).
    *   Normalization to USD will still be important.
6.  **Update `test_connectors.py`:** Adapt the script to test the new user-data-focused connector methods.
7.  **Frontend Adjustments:** Modify frontend JavaScript to correctly interpret and display personal volume data.

## Active Decisions and Considerations
- **Fundamental Shift:** The project is now about **personal volume tracking**, not market volume. All technical decisions must align with this.
- **API Key Permissions:** User's API keys will need permissions to read trade history and potentially other account-specific data. This should be communicated.
- **Data Privacy & Security:** Handling personal trading data and API keys requires utmost attention to security at all stages.
- **Definition of "Volume":** For personal trades, volume is typically the quote currency value of each trade (e.g., `price * quantity`). This needs to be consistently calculated and aggregated.
- **Historical Data Derivation:** If exchanges only provide raw trade lists, the backend will need logic to sum these into daily (or other granularity) personal volume figures per market.
