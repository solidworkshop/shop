# CHANGELOG

## v1.0.0
- Initial modular Flask app with SQLite persistence
- Public shop: home, product detail, cart, checkout, about, FAQ, contact
- Admin console (Flask-Login) with master switches, per-event toggles
- Automation presets with global start/stop and token-bucket QPS per channel
- Request inspector + logs + counters (pixel, capi, dedup, margin Σ, PLTV Σ)
- robots.txt + meta noindex + X-Robots-Tag header
- Catalog manager (editable items, add/delete, basic multicurrency field)
- CAPI dry-run if creds not provided, real forwarding if configured


## v1.0.1
- Added Chaos toggles UI (drop events, omit params, malformed payloads)
- Added Seed control for deterministic randomness
- Added per-event interval controls and persistence
- Added Pixel install checker API and UI
- Embedded JS pixel snippet + test beacon button; added /pixel-collect to log beacons
