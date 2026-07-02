release: python manage.py makemigrations core --noinput && python manage.py migrate --noinput
web: gunicorn config.wsgi --log-file -
worker: celery -A config worker --loglevel INFO
beat: celery -A config beat --loglevel INFO
