import os

from app import create_app

app = create_app()

# Assure que l'instance folder existe
os.makedirs(app.instance_path, exist_ok=True)

# Init DB si absente (utile en déploiement WSGI)
_db_file = os.path.join(app.instance_path, app.config['DATABASE'])
if not os.path.exists(_db_file):
    with app.app_context():
        from db import init_db
        init_db()
        print('DB créée automatiquement (WSGI):', _db_file)

# Pour gunicorn :
# gunicorn -w 2 -b 0.0.0.0:8000 wsgi:app
