# Changelog

## v1.2.0
- Counters show **Margin Events** and **PLTV Events** (count of events carrying those fields).
- Added **% of Purchases with Profit Margin** and **% with PLTV** controls (0–100, default 100%).
- Added **Manual Send (raw JSON)** card with Validate and Send.
- Restored **Chaos** toggles (Drop, Omit, Malformed).
- Moved **Health & Pixel Check** after Automation; added **Open Inspector** link.
- Automation respects **Send Pixel** and **Send CAPI** switches (manual send unaffected).
- CAPI robustness: IP validation, synthetic `fbp` when cookie absent (avoids 2804050).
- Kept live counters/status polling and request inspector/logs pages.
- Hidden Graph API badge from UI.
- Build number set to v1.2.0 on the Admin dashboard.
