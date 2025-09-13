# Demo Store + Meta Pixel & CAPI Tester — v1.4.1 (FULL)

**This ZIP contains ALL files**. Includes an **auto-migration** that adds the missing `user.pw_hash` column and seeds a hash if blank.

## Fix for `no such column: user.pw_hash`
- v1.4.1 runs a lightweight SQLite migration at startup:
  - Adds `pw_hash` column to `user` if missing.
  - Sets a hash for any row with empty `pw_hash` using `ADMIN_PASSWORD`.

## Render setup
- Build: `pip install -r requirements.txt`
- Start: `gunicorn -k gthread -w 1 app:app`
- Env:
  - `PIXEL_ID`, `ACCESS_TOKEN`, `GRAPH_VER=v20.0`, `BASE_URL=https://your-app.onrender.com`
  - `TEST_EVENT_CODE` — leave blank for **live** Overview; fill for **Test Events**
  - `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `SECRET_KEY`
  - `WEB_CONCURRENCY=1`

## If Events Manager shows no recent activity
1. In **/admin**, toggle **Use Test Event Code** OFF (sends live events).
2. **/admin → Health → Show Config Summary** must show `pixel_id_present: true`, `access_token_present: true`.
3. Ensure `BASE_URL` domain is allowed under Pixel **Allowed Domains**.
4. Click **Send Live Purchase Now** to force a live CAPI event.
5. Check **/admin → Logs** for `ok` or any Graph error text.

