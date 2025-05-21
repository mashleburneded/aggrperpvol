# Technical Context: Personal Aggregated Perpetual Volume Dashboard

## Technologies Used
- **Backend:**
    - Python 3.9+
    - FastAPI (web framework)
    - Uvicorn (ASGI server)
    - Pydantic (data validation and settings management)
    - SQLAlchemy (ORM for PostgreSQL)
    - `asyncpg` (Async PostgreSQL adapter, replacing `psycopg2-binary` for async operations)
    - `python-dotenv` (environment variable management)
    - `httpx` (asynchronous HTTP client for exchange APIs and CoinGecko)
    - `cryptography` (for Fernet encryption of API keys)
    - `redis` (Python client for Redis cache)
    - `APScheduler` (for background tasks/scheduling)
- **Frontend:**
    - HTML5
    - CSS3 (Tailwind CSS via CDN)
    - Vanilla JavaScript
    - Chart.js (for historical data charting)
- **Database:** PostgreSQL
- **Cache:** Redis
- **Containerization:** Docker, Docker Compose
- **Version Control:** Git (assumed)

## Development Setup
- **Python Environment:** Python 3.9+ with `pip` for package management (`requirements.txt`).
- **Docker Desktop:** Required for running `docker-compose` environment.
- **Code Editor:** VS Code (current environment).
- **`.env` file:** For local backend configuration (database URL, Redis URL, `APP_SECRET_KEY`). API keys are managed via the application's secure storage.
- **Exchange APIs & SDKs (Initial Review - *Focus shifted to User Data Endpoints*):**
    - **General Requirement:** Connectors for WOO X and Paradex must target authenticated, private endpoints that provide access to **the user's trade history or account-specific volume summaries**. Public market data endpoints are no longer the primary target.
    - **WOO X:** V1 API.
        - **User Trade History (Recent):** `GET /v1/client/trades`. Requires authentication. Supports `symbol`, `start_t`, `end_t`, `page`, `size`. Fetches trades for the last 3 months.
        - **User Trade History (Archived):** `GET /v1/client/hist_trades`. Requires authentication. Supports `symbol`, `start_t` (**required**), `end_t` (**required**), `fromId` (cursor), `limit`. Fetches trades older than 3 months.
        - Both endpoints provide execution details: `id`, `symbol`, `order_id`, `executed_price`, `executed_quantity` (base), `is_maker`, `side`, `fee`, `fee_asset`, `executed_timestamp`.
    - **Paradex:** (Documentation: `https://docs.paradex.trade/`)
        - **User Fills Endpoint (Detailed Trades)**: `GET /v1/account/list-fills`
            - **Description**: Returns a list of matched orders (fills) sent to chain for settlement. This is the primary endpoint for historical personal volume.
            - **Authentication**: JWT required (private endpoint).
            - **Query Parameters**:
                - `market` (string, Optional): Market symbol (e.g., "BTC-USD-PERP").
                - `start_at` (integer, Optional): Start time (Unix milliseconds).
                - `end_at` (integer, Optional): End time (Unix milliseconds).
                - `page_size` (integer, Optional, 1-5000, default 100): Number of records per page.
                - `cursor` (string, Optional): For pagination.
            - **Response**: Contains `results` (list of fill objects), `next` (cursor for next page), `prev` (cursor for previous page). Each fill object is expected to contain details like price, quantity, timestamp, fee, side, etc. (17 properties).
        - **Aggregated Volume Endpoint (Secondary/Less Ideal)**: `GET /v1/account/history?type=volume`
            - Provides aggregated volume data with timestamps but lacks market filtering and detailed trade info, making it less suitable for our primary goal of 1-2 years of daily volume per market.

## Technical Constraints & Considerations
- **API Authentication:** All exchange interactions will now require robust handling of user-provided API keys (and JWT for Paradex) for accessing private user data.
- **API Rate Limits:** Private endpoints often have stricter rate limits. Connectors must handle these carefully. (Paradex `GET /*` private endpoints: 40 req/sec or 600 req/min per account).
- **Data Structure from User Endpoints:** The format of user trade history or account volume summaries will vary significantly between exchanges. Connectors must parse these diverse structures and extract/calculate daily USD-equivalent volume for the user.
- **Historical Data Completeness:** The depth and availability of user trade history can vary.
- **Paradex API for User Data:** The `GET /v1/account/list-fills` endpoint is well-suited for fetching historical trade data.
- **Scalability (User-Specific Context):** While the system is for a single user's data on WOO X and Paradex, fetching and processing potentially large trade histories (e.g., 1-2 years) still requires efficient data handling and database operations.
- **Security:** Paramount due to handling of API keys that access personal user accounts. Secure storage, transmission, and usage are critical.
- **Volume Calculation from Trades:** If exchanges provide raw trade lists, the backend will need to sum these up to get daily volumes per market, then convert to USD. This involves handling trade price, quantity, and timestamp for each trade.
- **Real-time Personal Volume:** Defining and fetching "real-time" or "current 24h" personal volume will depend on what data the exchange APIs make available (e.g., recent trades, a 24h summary of user account activity).

## Dependencies (from `requirements.txt`)
- `fastapi`
- `uvicorn[standard]`
- `pydantic`
- `python-dotenv`
- `asyncpg` # For async SQLAlchemy with PostgreSQL
- `SQLAlchemy`
- `redis`
- `apscheduler`
- `httpx`
- `cryptography`
- (`psycopg2-binary` might be removed if no longer needed for any sync operations)

## Tool Usage Patterns (for this project)
- (Largely the same, but research focus shifts to private API docs)
- `write_to_file`, `replace_in_file`, `execute_command`, `read_file`.
- `use_mcp_tool` (e.g., `firecrawl_scrape`, `search_google`): For researching WOO X and Paradex API documentation for **user data endpoints**.
- `ask_followup_question`.
