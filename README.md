# Aggregated Perpetual Volume Dashboard

This project provides a dashboard to display aggregated real-time and historical perpetual trading volume from various exchanges.

## Features
- Fetches volume data from Bybit, WOO X, Hyperliquid.xyz, and Paradex.trade.
- Displays current aggregated volume.
- Shows historical aggregated volume charted over 1-2 years.
- Allows users to securely input their API keys.
- Provides an endpoint for embedding volume data on external websites.
- Frontend built with HTML, Tailwind CSS, and JavaScript.
- Backend built with Python (FastAPI), PostgreSQL, and Redis.

## Project Structure
- `frontend/`: Contains the HTML, CSS, and JavaScript for the dashboard UI.
- `backend/`: Contains the FastAPI application for data fetching, aggregation, and API services.
- `docker-compose.yml`: For local development setup of backend, database, and cache.

## Setup and Running

### Prerequisites
- Docker
- Docker Compose

### Local Development
1.  **Configure API Keys:**
    Create a `.env` file in the `backend/` directory:
    ```env
    # backend/.env
    DATABASE_URL=postgresql://user:password@db:5432/appdb
    REDIS_URL=redis://redis:6379
    
    # Add your exchange API keys here (these will be managed via the UI eventually)
    # BYBIT_API_KEY=your_bybit_api_key
    # BYBIT_API_SECRET=your_bybit_api_secret
    # WOOX_API_KEY=your_woox_api_key
    # WOOX_API_SECRET=your_woox_api_secret
    # HYPERLIQUID_API_KEY=your_hyperliquid_api_key # Or relevant auth details
    # HYPERLIQUID_API_SECRET=your_hyperliquid_api_secret
    # PARADEX_API_KEY=your_paradex_api_key # Or relevant auth details
    # PARADEX_API_SECRET=your_paradex_api_secret

    # Secret key for encrypting user-provided API keys in the database
    APP_SECRET_KEY=generate_a_strong_random_secret_key_here 
    ```
    Replace `generate_a_strong_random_secret_key_here` with a securely generated key (e.g., using `openssl rand -hex 32`).

2.  **Build and Run Containers:**
    ```bash
    docker-compose up --build
    ```

3.  **Accessing the Services:**
    - Backend API: `http://localhost:8000` (Swagger UI at `http://localhost:8000/docs`)
    - Frontend Dashboard: `http://localhost:8081`
    - PostgreSQL: Accessible on `localhost:5432` (from host) or `db:5432` (from other containers)
    - Redis: Accessible on `localhost:6379` (from host) or `redis:6379` (from other containers)

## Backend API Endpoints
- `/api/keys` (POST, GET, DELETE): Manage user API keys for exchanges.
- `/api/volume/historical` (GET): Fetch historical aggregated volume.
  - Params: `start_date`, `end_date`, `granularity` (daily, weekly, monthly)
- `/api/volume/current` (GET): Fetch current aggregated 24h volume.
- `/public/latest-volume` (GET): Public endpoint for website embedding.
- `/ws/live-volume` (WebSocket): Stream real-time updates for current aggregated volume.

## TODO
- Implement all backend services and API endpoints.
- Implement frontend JavaScript logic for API interaction, charting, and WebSocket communication.
- Enhance UI/UX and styling.
- Add comprehensive error handling and logging.
- Write unit and integration tests.
