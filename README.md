# X-Analysis (Django Backend)

This project now uses a Django backend with a dedicated dashboard app.

## Structure

- `xsignal_django/` Django project config (`settings.py`, `urls.py`, ASGI/WSGI)
- `dashboard/` Django app with sentiment services, views, URLs, templates, and static assets
- `manage.py` Django management entrypoint
- `app.py` convenience launcher that runs Django on port `8050`

## Run

1. Install dependencies:
	- `pip install -r requirements.txt`
2. Run migrations:
	- `python manage.py migrate`
3. Start server:
	- `python manage.py runserver 0.0.0.0:8050`
	- or `python app.py`

Open: `http://localhost:8050/`



sudo nano /etc/nginx/sites-available/xsignal

sudo ln -sf /etc/nginx/sites-available/xsignal /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default