# Progress: Personal Aggregated Perpetual Volume Dashboard

## What Works
*(Cumulative list of accomplishments)*

- **(Initial) Project Scaffolding:** Base directory structure, Docker setup, FastAPI app, core components (config, security, DB), models, schemas, CRUD stubs, API router stubs, basic frontend files, and initial Memory Bank files created.
- **(Initial) Backend Async Setup:** Database core (`database.py`) updated for async operations; `main.py` adapted for async lifespan and scheduler. `requirements.txt` includes `asyncpg`.
- **(Initial) Frontend UI for Granular Fetching & API Keys:** `index.html` updated with UI controls for platform selection, date ranges, manual fetch buttons, API key inputs, "Save All API Keys" button, Chart.js CDN, and chart canvas. `js/app.js` includes basic logic for these elements and API key saving.
- **(Initial) Volume Normalization (Placeholder):** `AggregationService` included a CoinGecko-based `_get_usd_price` for current prices.
- **(Initial) Exchange Connector Stubs:** Basic connector classes created for Bybit, WOO X, Hyperliquid, and Paradex.
- **(Correction) Project Objective Clarified:** The project's primary goal is now understood to be tracking **the user's personal trading volume**, not general market volume.
- **(New) Memory Bank Overhaul:**
    - `projectbrief.md`: Rewritten to reflect focus on personal trading volume.
    - `productContext.md`: Rewritten to align with personal volume tracking.
    - `systemPatterns.md`: Updated to show data flow for personal volume and user-specific API calls.
    - `techContext.md`: "Exchange APIs" and "Technical Constraints" sections updated for user data focus, including initial findings for Paradex `GET /v1/account/history`.
    - `activeContext.md`: Updated to reflect the project pivot and next steps (API research for user data).
    - This `progress.md` file is being updated to reflect the pivot.
- **(New) Testing Script Created (`test_connectors.py`):**
    - A Python script (`aggrperpvol/backend/test_connectors.py`) was created to help the user manually test individual exchange connectors by providing API keys and symbols. This script was based on the *previous incorrect assumption* of fetching market data and will need to be adapted once user-specific API endpoints are identified.
- **(Update) `ParadexConnector` Revised:** Updated to use `GET /v1/account/list-fills` for fetching user historical fills and processing them into daily kline-like summaries.
- **(Update) `WooXConnector` Revised:** Updated to use `GET /v1/client/trades` and `GET /v1/client/hist_trades` for fetching user historical trades and processing them into daily kline-like summaries.
- **(Update) `AggregationService` Revised:** Imports and connector/symbol mappings updated to focus solely on WOO X and Paradex.
- **(Update) `test_connectors.py` Revised:** Script updated to focus on WOO X and Paradex, and to test user-specific data fetching methods.
- **(Update) Frontend Adjustments (`app.js`, `index.html`):**
    - `aggrperpvol/frontend/js/app.js`: Removed references to Bybit and Hyperliquid from API key constants and `platformInputs`.
    - `aggrperpvol/frontend/index.html`: Removed Bybit and Hyperliquid API key input sections and updated the platform selection dropdown. Removed inline script and ensured external `app.js` is linked.

## What's Left to Build (Key Next Steps - *Revised after project pivot and scope reduction*)

1.  **API Endpoint Research (User-Specific Data - WOO X, Paradex - CRITICAL):**
    *   For **WOO X**: Identify the correct private API endpoints and parameters to fetch:
        *   The user's historical trade execution data (ideally with symbol, price, quantity, timestamp, fee, side).
        *   The user's current (e.g., last 24h) personal trading volume summary (if available directly from an endpoint).
    *   For **Paradex**:
        *   **Confirmed Endpoint for Historical Fills**: `GET /v1/account/list-fills` (from `docs.paradex.trade`) is suitable.
            - Supports `market` filtering.
            - Supports `start_at` and `end_at` (Unix ms) for time range.
            - Supports pagination via `cursor` and `page_size`.
            - Returns detailed fill objects.
        *   The previously noted confusion about deprecated docs vs. `developers.paradex.io` seems resolved, with `docs.paradex.trade` being the correct current source for this endpoint.
    *   Document all findings (e.g., in `techContext.md` or a new `api_research.md`).
2.  **Revise Exchange Connectors (WOO X, Paradex - Major Overhaul):**
    *   Rewrite `get_historical_klines` (rename to e.g., `get_user_historical_volume`) in WOO X and Paradex connectors to:
        *   Use the newly identified user-specific authenticated endpoints.
        *   Handle authentication (API keys for WOO X, JWT for Paradex) for every call.
        *   Parse the specific response structures for user trade history/volume.
        *   Process raw trade data to calculate daily (or other granularity) USD-equivalent volume per symbol for the user. This will involve handling price, quantity, and side of trades.
    *   Rewrite `get_latest_24h_volume` in WOO X and Paradex connectors to:
        *   Use appropriate user-specific endpoints to get/calculate the user's personal 24h trading volume for the platform.
        *   Return this as `schemas.ExchangeVolumeInfo` (with `volume_24h_usd` correctly representing personal USD volume).
3.  **Revise Data Models & Schemas:**
    *   Evaluate if `models.HistoricalVolume` and `schemas.HistoricalKline` / `schemas.AggregatedHistoricalVolume` are still appropriate. If we are storing daily summaries of *personal* volume, they might be. If storing individual trades, new models/schemas will be needed.
    *   The `volume` field in `schemas.HistoricalKline` (if still used) must clearly represent the user's trade volume in quote currency for that period.
4.  **Revise `AggregationService`:**
    *   Update logic to correctly process and aggregate data from the revised connectors (which now provide personal trade data/volume).
    *   The `_normalize_historical_volume_record` and `_get_usd_price` methods will be crucial for converting trade execution values (price * quantity) into a consistent USD value if not already provided by the exchange in that form.
5.  **Update `test_connectors.py`:**
    *   Modify the script to call the revised connector methods.
    *   Update `TEST_API_KEYS` to ensure correct keys/permissions for accessing user trade data are used.
    *   Adjust expected outputs based on user data.
6.  **Frontend Adjustments:**
    *   Ensure `js/app.js` correctly fetches, interprets, and displays **personal aggregated volume**.
    *   The chart should display historical **personal trading volume**.
7.  **Thorough Testing (Post-Revisions):** Unit, integration, and end-to-end testing focusing on the accuracy of personal volume data.

## Current Status

**Timestamp: 2025-05-18 02:03 AM UTC+2**
- **Frontend Adjustments Complete:**
    - `aggrperpvol/frontend/js/app.js` updated to remove Bybit/Hyperliquid.
    - `aggrperpvol/frontend/index.html` updated to remove Bybit/Hyperliquid UI elements and correctly link `app.js`.
- **`test_connectors.py` Updated:** The test script now focuses on WOO X and Paradex, and is adapted for testing user-specific data fetching.
- **Path Forward:** The next major phase is "Thorough Testing (Post-Revisions)". This involves the user running the application, providing API keys, and verifying that personal volume data is fetched, aggregated, and displayed correctly for WOO X and Paradex.

**Previous Status (Timestamp: 2025-05-18 01:58 AM UTC+2)**
- **`AggregationService` Updated:** The service at `aggrperpvol/backend/app/services/aggregation_service.py` has been revised to remove Bybit and Hyperliquid connectors and symbols, focusing only on WOO X and Paradex.
- **New Paradex API Links Investigated:**
    - `GET /account/transactions`: Provides a list of user-initiated transactions. Noted in `activeContext.md` as a potential alternative to `GET /v1/account/list-fills` if the latter proves insufficient, though `list-fills` is preferred for detailed trade data.
    - `GET /account/info`: Appears to provide general account information, not directly relevant for historical volume.
- **`activeContext.md` Updated:** A note regarding the Paradex `GET /account/transactions` endpoint was added.
- **Path Forward:** The next step was to update `test_connectors.py`.

**Previous Status (Timestamp: 2025-05-18 01:36 AM UTC+2)**
- **Project Scope Refined:** Focus narrowed to WOO X and Paradex for personal volume tracking.
- **Memory Bank Revision Complete:** All core memory bank files (`projectbrief.md`, `productContext.md`, `systemPatterns.md`, `techContext.md`, `activeContext.md`, and this `progress.md`) updated to reflect the scope change.
- **Paradex API Research Update:** Confirmed `GET /v1/account/list-fills` from `docs.paradex.trade` as the appropriate endpoint for fetching historical user fills, with necessary parameters for filtering by market, time range, and pagination.
- **Previous Work Assessment:** Much of the prior connector and service logic (focused on market data for all four initial exchanges) will require significant rework or replacement. The existing `test_connectors.py` script is also based on the old premise.
- **Path Forward Defined:** The immediate next step was to revise `AggregationService`, then investigate new Paradex links.

**Previous Status (Timestamp: 2025-05-18 01:39 AM UTC+2)**
- **Paradex API Research Update:**
    - `GET /v1/account/history` with `type="volume"` confirmed as user-specific.
    - SDK analysis suggests a `get_fills()` method, implying an underlying API for detailed trade data, which needs to be identified.
    - Further details on filtering and granularity for both potential endpoints are pending.
- **Previous Work Assessment:** Much of the prior connector and service logic (focused on market data for all four initial exchanges) will require significant rework or replacement. The existing `test_connectors.py` script is also based on the old premise.
- **Path Forward Defined:** The immediate next step is to continue API endpoint research for user-specific data for WOO X, and further detail for Paradex (confirming the "fills" endpoint and parameters for `/v1/account/history`).
- **Previous Work Assessment:** Much of the prior connector and service logic (focused on market data for all four initial exchanges) will require significant rework or replacement. The existing `test_connectors.py` script is also based on the old premise.
- **Path Forward Defined:** The immediate next step is to continue API endpoint research for user-specific data for WOO X, and further detail for Paradex.

**Previous Status (Timestamp: 2025-05-18 00:38 AM UTC+2 - *Based on previous, incorrect understanding*)**
- All four exchange connectors were (incorrectly) refined for market data.
- Memory bank files were updated based on that incorrect understanding.

## Detailed Plan for Next Steps:

**1. API Endpoint Research for User Data (WOO X, Paradex - CRITICAL - Ongoing):**
    *   For **WOO X**:
        *   Identify endpoints for fetching user's historical trade executions (filled orders). Required data: symbol, price, quantity, timestamp, side (buy/sell), fees.
        *   Identify endpoints for fetching user's 24-hour trading volume summary (if available directly).
        *   Understand authentication mechanisms thoroughly (API Key + Secret).
    *   For **Paradex**:
        *   Further investigate `GET /v1/account/history` with `type="volume"`:
            *   No further research needed for Paradex historical fills endpoint itself, but implementation details (response structure of fill objects) will be handled during connector development.
    *   Document findings (e.g., in `techContext.md` or a dedicated research document).
**2. Backend Re-Implementation (Iterative for WOO X, Paradex - *Paradex research for fills complete*):**
    *   **Revise `schemas.HistoricalKline` / `schemas.AggregatedHistoricalVolume` or create new ones** if the structure of daily personal volume summaries is different from market klines.
    *   **Revise `models.HistoricalVolume`** accordingly.
    *   **For each connector:**
        *   Implement methods to fetch user trade history.
        *   Implement methods to calculate daily personal volume in USD for each traded market from the trade history.
        *   Implement methods to fetch/calculate current 24h personal volume in USD.
    *   **Revise `AggregationService`:**
        *   Adapt `fetch_and_store_historical_data_for_platform` to store daily summaries of personal volume.
        *   Adapt `get_historical_aggregated_volume` and `get_current_aggregated_volume` for personal data.
        *   Ensure `_get_usd_price` (CoinGecko) is used correctly if trades are not in USD.
    *   **Update `test_connectors.py`** to test the new user-data methods.
**3. Frontend Adaptation (*Pending Backend Changes*):**
    *   Ensure UI correctly displays personal volume data.
    *   Verify API key input and management flow.
**4. Testing & Deployment:** As previously outlined, but focused on personal volume accuracy.

## Known Issues & Uncertainties
- **Availability of User Trade History APIs:** The feasibility and granularity of fetching historical personal trade data across all exchanges.
- **Data Format Consistency:** User trade data formats will vary; robust parsing and calculation logic needed.
- **Historical Price Data for Non-USD Trades:** If trades are in non-USD quote currencies, accurate historical prices at the time of each trade will be needed for USD conversion. CoinGecko's current price endpoint is insufficient for past trades.
- **Paradex API for User Data (Granularity/Filtering):** The `GET /v1/account/list-fills` endpoint provides necessary granularity and filtering for historical trade data over 1-2 years.
