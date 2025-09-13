# Changelog

## v1.3.3
- **Start with Intervals reliability & UX**
  - API now tolerates repeated “start” clicks (returns current state instead of failing).
  - Safer interval parsing with fallbacks; values persisted to KV.
  - Added `/admin/api/automation/ping` to fire a one-off Purchase for debugging.
  - UI shows inline success/error messages and disables buttons during requests.
- Build badge set to **v1.3.3**.

Tip: for thread-based automation on Render, set **WEB_CONCURRENCY=1** to avoid multiple worker processes each running their own timers.
