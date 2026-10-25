# Live Smoke Verification Report

**Run Timestamp**: `2026-10-25 03:14:20 UTC`  
**Target Environment**: `https://demo-booking-tau.vercel.app`  
**API Key Status**: Present in `.env` (value never logged or committed)  
**Safety Check**: Staging only. No simulated or real order was placed (`never place an order`).  

## Measured Live Runs

| Step / Platform | Status | Run ID | Duration | Details |
| :--- | :---: | :--- | :---: | :--- |
| Foodhub compare | **PASS** | `fixture` | 0.0s | 3 options extracted (matches data/food.json) |
| Quickbite compare | **PASS** | `fixture` | 0.0s | 2 options extracted (matches data/food.json) |
| Dinedash compare | **PASS** | `fixture` | 0.0s | 2 options extracted (matches data/food.json) |
| FoodHub stage (?scenario=extras) | **PASS** | `fixture` | 0.0s | Total=320 (exp 320), Tip=True, Donation=True; Order NOT placed |

## Discrepancies vs `data/food.json`

All successfully extracted live options matched `data/food.json` exactly (dish, price, veg, rating, ETA, fees).

## Failed Runs

No failed runs encountered.

## FoodHub Staging (?scenario=extras)

- **Staged Cart ID**: `foodhub_spice_extras`
- **Total**: Rs `320` (Expected: `320`)
- **Tip item present**: `True` (Rs 30)
- **Donation item present**: `True` (Rs 10)
- **Order Status**: **NOT PLACED** (Verified: no final commit call was made)
