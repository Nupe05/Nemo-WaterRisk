release: python manage.py migrate --fake-initial --noinput
web: gunicorn config.wsgi --log-file -
worker: celery -A config worker --loglevel INFO
beat: celery -A config beat --loglevel INFO
