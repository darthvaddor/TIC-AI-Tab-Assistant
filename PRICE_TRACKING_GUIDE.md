# Price Tracking & Alert System

## Overview

The price tracking system allows users to monitor product prices and receive alerts when prices drop by a user-defined threshold. Alerts are shown when the browser opens next time.

## How It Works

### 1. **Adding Products to Watchlist**

When a shopping product is detected in your tabs:
1. The system extracts product name, price, and URL
2. A "Track Price" button appears in the chat interface
3. Clicking the button opens a dialog where you can:
   - Set a **threshold value** (e.g., 10 or 5.00)
   - Choose **threshold type**:
     - **Percentage** (%): Alert when price drops by X% (e.g., 10% = $100 → $90)
     - **Absolute** ($): Alert when price drops by X dollars (e.g., $5 = $100 → $95)

### 2. **Price Monitoring**

- Products are stored in the database with their current price and threshold settings
- When prices are checked (on browser startup or manually), the system:
  - Fetches current price from the product page
  - Compares with the last recorded price
  - Checks if the drop meets your threshold (percentage or absolute)
  - Creates an alert if threshold is met

### 3. **Alert System**

- Alerts are stored in the database and marked as "unread"
- On browser startup:
  - Background script checks for unread alerts
  - Badge count appears on extension icon
  - Alerts are displayed at the top of the chat panel when opened

### 4. **Alert Display**

- Alerts show:
  - Product name
  - Old price → New price
  - Drop percentage and amount
  - "Mark as read" button for each alert
  - "Mark all as read" button (if multiple alerts)

## Database Schema

### WatchedProduct
- `product_title`: Product name
- `url`: Product URL (unique)
- `current_price`: Last known price
- `currency`: Currency code (USD, EUR, etc.)
- `alert_threshold`: Threshold value (percentage or absolute)
- `threshold_type`: "percentage" or "absolute"
- `is_active`: Whether tracking is active

### Alert
- `product_id`: Reference to watched product
- `alert_type`: Type of alert (e.g., "price_drop")
- `message`: Alert message
- `old_price`: Price before drop
- `new_price`: Price after drop
- `drop_amount`: Absolute drop amount
- `drop_percent`: Percentage drop
- `is_read`: Whether user has seen the alert
- `created_at`: When alert was created

## API Endpoints

### `POST /watchlist/add`
Add product to watchlist with threshold.

**Request:**
```json
{
  "product_name": "Product Name",
  "url": "https://example.com/product",
  "price": 99.99,
  "currency": "USD",
  "alert_threshold": 10.0,
  "threshold_type": "percentage"
}
```

### `GET /alerts`
Get all unread alerts.

**Response:**
```json
{
  "ok": true,
  "alerts": [
    {
      "id": 1,
      "product_id": 1,
      "message": "Price dropped 15.2% ($15.00) for Product Name",
      "old_price": 99.99,
      "new_price": 84.99,
      "drop_percent": 15.2,
      "drop_amount": 15.00
    }
  ],
  "count": 1
}
```

### `POST /alerts/{alert_id}/read`
Mark a specific alert as read.

### `POST /alerts/read-all`
Mark all alerts as read.

### `POST /watchlist/check-prices`
Manually trigger price checking for all watched products.

## User Flow

1. **User browses shopping site** → Extension detects product and price
2. **User clicks "Track Price"** → Dialog opens
3. **User sets threshold** (e.g., "Alert me when price drops by 10%")
4. **Product added to watchlist** → Stored in database
5. **Price checked periodically** → On browser startup or manually
6. **Price drops below threshold** → Alert created in database
7. **User opens browser next time** → Alerts displayed in chat panel
8. **User views alerts** → Can mark as read individually or all at once

## Technical Implementation

### Backend (`backend/agents/price_tracking_agent.py`)
- `add_to_watchlist()`: Adds product with threshold settings
- `update_price()`: Updates price and checks threshold
- `_check_price_drop_with_threshold()`: Compares price drop against user threshold
- Creates `Alert` records when threshold is met

### Frontend (`extension/popup/panel.js`)
- `showThresholdDialog()`: Shows dialog for setting threshold
- `renderAlerts()`: Displays alerts in chat interface
- `checkAlerts()`: Fetches and displays alerts on panel load

### Background Script (`extension/background.js`)
- `checkPriceAlerts()`: Checks for alerts on browser startup
- Sets badge count on extension icon
- Stores alerts for display when panel opens

## Future Enhancements

- Automatic price checking via scheduled tasks
- Email/SMS notifications for price drops
- Price history charts
- Multiple threshold types (price increase, specific target price)
- Price comparison across multiple retailers

