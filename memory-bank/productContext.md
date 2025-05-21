# Product Context: Personal Aggregated Perpetual Volume Dashboard

## Purpose
This project aims to provide the user (Mashle) with a centralized dashboard for tracking and visualizing **their personal aggregated perpetual trading volume** from their accounts on multiple cryptocurrency exchanges. It serves the user's need for a consolidated view of **their own trading activity** across different platforms.

## Problems Solved
- **Personal Data Fragmentation:** The user currently needs to log into multiple exchange accounts or use various tools to get a sense of **their total personal trading volume**.
- **Personal Performance Tracking:** Lack of a single, aggregated view of **personal volume** makes it harder for the user to gauge **their overall trading activity levels and trends** over time.
- **API Key Management:** The user needs a secure way to manage API keys for **their different exchange accounts** to enable the dashboard to pull **their personal trading data**.
- **(Potentially) Private Data Embedding:** The user might want a way to view this aggregated **personal volume data** in a private, convenient manner, possibly embedded if secured appropriately.

## How it Should Work
- **Data Ingestion:** The backend system will connect to specified exchanges (WOO X, Paradex) using **the user's provided API keys**, which must have permissions to read trade history or account volume summaries.
- **Historical Personal Data:** The system will fetch and store **the user's historical daily trading volume data** for the past 1-2 years for relevant perpetual contracts they have traded on WOO X and Paradex. This will likely involve processing trade execution history.
- **Real-time Personal Data:** The system will periodically fetch **the user's latest 24-hour personal trading volume**.
- **Aggregation:** The backend will aggregate **the user's personal volumes** from all their connected platform accounts, normalizing them to a common quote currency (e.g., USD).
- **Frontend Display:**
    - The user can input and manage their API keys for different platforms through a secure interface.
    - The dashboard will display **the user's total aggregated current (e.g., 24h) personal volume**.
    - **Historical aggregated personal volume** will be displayed in chart format (e.g., daily/weekly/monthly over 1-2 years).
    - The UI will be themed with #ffd230 (gold) and #000000 (black background).
- **User Experience:** The dashboard should be visually appealing, easy to use, and responsive. It should clearly indicate data freshness and handle loading/error states gracefully, providing insights into **the user's trading patterns across exchanges**.

## User Experience Goals
- **Clarity:** Provide a clear, at-a-glance understanding of **the user's aggregated personal trading volume**.
- **Convenience:** Offer a single point of access for **their personal volume data** from multiple exchange accounts.
- **Trust & Security:** Ensure API keys for **their accounts** are handled with utmost security.
- **Personalization:** The dashboard is inherently personalized as it reflects **the user's own trading data**.
- **Performance:** The dashboard should load quickly and update efficiently with **the user's data**.
