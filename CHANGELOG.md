# Changelog

## v1.3.2
- **Admin layout**: switched to a **single-column** stack to simplify scanning on smaller screens.
- **Back to store** link added to the admin header.
- **Pixel Check**: clearer, timestamped results in the UI.
- **FBP fix**: when `_fbp` cookie is missing, we now generate an **ephemeral** `fb.1.*` value per request (not persisted), so it won’t be the same across all events.
- Build badge auto-updates to **v1.3.2**.

(Previous: v1.3.1 — events visibility helpers, catalog cost/description, auto-migrations; v1.3.0 — catalog manager; v1.2.0 — automation percentages, manual send UI, chaos toggles.)
