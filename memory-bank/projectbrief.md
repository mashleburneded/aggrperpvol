# Project Brief: Personal Aggregated Perpetual Volume Dashboard

## Brief Overview
This project aims to build a dashboard that aggregates and displays **the user's personal real-time and historical perpetual trading volume data** from their accounts on multiple cryptocurrency exchanges. It will provide a user-friendly interface for managing API keys (necessary for accessing personal account data) and viewing this aggregated personal volume.

## Goals
- Develop a frontend dashboard to visualize **the user's aggregated personal trading volume**.
- Implement a robust backend system to fetch, store, and process **user-specific trading data** from WOO X and Paradex.trade using the user's API keys.
- Securely manage user API keys for these platforms.
- Provide **historical aggregated personal volume data** charted over the last 1-2 years.
- Offer a mechanism for real-time updates of **current personal volume**.
- Ensure the UI is aesthetically pleasing with a theme of #ffd230 (gold) and #000000 (black background).
- Design the system to handle data fetching and processing efficiently for a single user's accounts.

## Core Requirements
- **Frontend:**
    - Utilize the provided base HTML/CSS/JS.
    - Display **aggregated personal volume** and historical charts of this volume.
    - Allow users to input and manage their API keys for each platform (essential for accessing their account data).
    - Implement real-time updates for the **current personal volume** display.
    - Adhere to the specified color theme.
- **Backend:**
    - Securely store and manage encrypted API keys.
    - Implement connectors for WOO X and Paradex.trade to fetch **user-specific trade history or account volume summaries**.
    - Fetch **historical daily personal trading volume data** for the past 1-2 years.
    - Aggregate **personal volume data** across the user's accounts on these platforms.
    - Provide REST API endpoints for frontend communication (API key management, historical personal volume, current personal volume).
    - Implement WebSocket for streaming real-time **personal volume** updates.
    - (Consider if a public embedding endpoint for personal volume is still desired or relevant).
- **Data:**
    - Store **historical daily personal trading volume data** persistently (e.g., in PostgreSQL). This might involve storing individual trades or daily summaries derived from trade history.
    - Potentially use caching (e.g., Redis) for frequently accessed aggregated **personal volume data**.
- **Deployment:**
    - Containerize frontend and backend applications using Docker.
    - Use `docker-compose` for local development.

## Key Stakeholders
- User (Mashle) - for tracking their personal trading activity.

## Timeline & Milestones (High-Level - *Needs re-evaluation based on new focus*)
1.  **Phase 1: Backend Core & API Key Management** (Largely still relevant)
    - Setup project structure, Docker, basic FastAPI app.
    - Implement API key storage (encrypted) and management APIs.
2.  **Phase 2: Exchange Connectors & Historical User Data Fetching (WOO X, Paradex)**
    - Research and implement connectors for WOO X and Paradex to fetch **user's historical trade data or account volume summaries**.
    - Implement service to aggregate and store this **personal historical data**.
3.  **Phase 3: API Endpoints & Frontend Integration (Historical Personal Volume - WOO X, Paradex)**
    - Develop API endpoints to serve **historical aggregated personal volume**.
    - Integrate frontend to display these historical charts.
4.  **Phase 4: Real-time Personal Volume & WebSocket**
    - Implement backend logic for **current/real-time personal volume** (e.g., 24h personal volume).
    - Add WebSocket for frontend updates.
5.  **Phase 5: UI Polish & Refinements**
    - Finalize UI/UX enhancements.
6.  **Phase 6: Testing & Deployment Prep**
    - Add tests, refine error handling, prepare for deployment.

## Assumptions
- User (Mashle) will provide necessary API keys with appropriate permissions (e.g., read trade history) for their accounts on the listed platforms.
- Each exchange API provides endpoints to access a user's trade history or summarized account trading volume with sufficient detail (timestamps, quantities, prices/quote values) to calculate daily USD-equivalent volume.
- The primary focus for historical data is daily granularity of the **user's trading volume**.
- "Real-time" volume implies fetching the user's recent (e.g., last 24h) trading volume periodically.
