#!/bin/sh
set -e

# Initialize admin user if not exists
python3 -c "
from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash
app = create_app()
with app.app_context():
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(username='admin', password_hash=generate_password_hash('admin123456'), src_interval_hours=1, notify_wechat=True))
        db.session.commit()
        print('[INIT] Admin user created: admin / admin123456')
    else:
        print('[INIT] Admin user already exists')
"

# SQLite + APScheduler 要求单 worker，否则定时任务重复执行且易触发 database is locked
WORKERS="${WEB_WORKERS:-1}"
exec gunicorn -w "$WORKERS" -b 0.0.0.0:${APP_PORT:-5000} --timeout 120 run:app
