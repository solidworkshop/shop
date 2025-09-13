
# Demo Shop + Admin (v1.6.0)

This is a clean, working Flask app with:
- Public shop (home/about/faq/contact) with seeded products
- Admin login (Flask-Login) with session handling
- Automation start/stop/status (JSON) with live badge updates
- Catalog admin with cost and HTML description
- SQLite persistence at `/var/tmp/app.db`
- Bootstrap styling, health checks, and `robots.txt` (noindex)

## Deploy to Render
- Build: `pip install -r requirements.txt`
- Start: `gunicorn -k gthread -w 1 -b 0.0.0.0:$PORT app:app`
- Health Check: `/healthz`

## Environment
- `SECRET_KEY` (required)
- `ADMIN_USERNAME` (default `admin`)
- `ADMIN_PASSWORD` (default `admin123`)

