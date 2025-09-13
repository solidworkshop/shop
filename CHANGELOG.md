# Changelog

## v1.3.1
- **Events Manager visibility helpers**:
  - Added **Use Test Event Code** toggle (Automation card). Turn **off** to send live server events without `test_event_code` so Data Sources "Recent activity" reflects them.
  - New **Send Live Purchase Now** button that bypasses test code for a one-shot live send.
  - `/admin/api/health` shows whether Pixel ID / Access Token are present and which Graph version/base URL are in use.
- **Catalog updates**:
  - Product has new fields: **cost** (REAL) and **description** (TEXT, accepts HTML).
  - SQLite columns are auto-added on first admin load.
  - Catalog Manager table now includes **Cost** and **Description (HTML)** columns.
  - Automation **Purchase** uses catalog price/cost when available (else falls back to random).
- Build badge auto-updates to **v1.3.1** on admin load.
