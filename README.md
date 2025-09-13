
# v1.3.1 Notes

### Seeing "no recent activity" in Events Manager?
- Turn **off** the "Use Test Event Code" switch in the Automation card to send **live** server events (no `test_event_code`).
- Or click **Send Live Purchase Now** in the Manual Send card to trigger a one-off live Purchase.
- Use **Show Config Summary** in Health to confirm PIXEL_ID, ACCESS_TOKEN, GRAPH_VER, and BASE_URL are set.

### Catalog
- Each product now has **price, cost, currency, image_url, description (HTML)**.
- When generating automated Purchases, we pick a random catalog item and compute `profit_margin = price - cost` when percentages include it.
