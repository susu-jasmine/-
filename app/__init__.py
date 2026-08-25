import os
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# 在 Engine 类级注册: 任何 SQLAlchemy 引擎新建连接时都触发，无论 Gunicorn
# prefork 还是多 worker，都能保证 WAL 设置不丢失。
@event.listens_for(Engine, 'connect')
def _sqlite_pragma_on_connect(dbapi_conn, _):
    """启用 WAL 模式 + 写锁超时，避免并发写时 database is locked。

    WAL 是数据库级持久属性，首次设置后永久生效。这里每次连接都执行，
    幂等无副作用，且能覆盖进程 fork 后的新连接。
    """
    # 仅对 SQLite 连接生效，避免误伤其他数据库
    if 'sqlite' not in type(dbapi_conn).__module__:
        return
    cur = dbapi_conn.cursor()
    cur.execute('PRAGMA journal_mode=WAL')
    cur.execute('PRAGMA busy_timeout=30000')   # 30s 写锁等待
    cur.execute('PRAGMA synchronous=NORMAL')    # WAL 下安全且更快
    cur.close()


def _auto_migrate(database):
    """SQLite 轻量自动迁移: 给已存在的表补齐新增列(仅 ALTER TABLE ADD COLUMN)。"""
    # (表名, 列名, 列定义SQL)
    additions = [
        ('users', 'bountyteam_token', "VARCHAR(128) DEFAULT ''"),
        ('users', 'bountyteam_interval_minutes', 'INTEGER DEFAULT 3'),
        ('users', 'bountyteam_auto_apply', 'BOOLEAN DEFAULT 0'),
        ('users', 'bountyteam_fast_poll', 'BOOLEAN DEFAULT 0'),
        ('users', 'bountyteam_poll_seconds', 'INTEGER DEFAULT 3'),
        # v1.4 360众测
        ('users', 'zc_cookie', 'VARCHAR(2048) DEFAULT ""'),
        ('users', 'zc_interval_seconds', 'INTEGER DEFAULT 3'),
        ('users', 'zc_auto_apply', 'BOOLEAN DEFAULT 0'),
        ('users', 'zc_fast_poll', 'BOOLEAN DEFAULT 0'),
        # v1.4 补天/漏洞盒子秒级
        ('users', 'src_poll_seconds', 'INTEGER DEFAULT 5'),
        ('users', 'src_fast_poll', 'BOOLEAN DEFAULT 0'),
        ('bounty_projects', 'apply_status', "VARCHAR(16) DEFAULT ''"),
        ('bounty_projects', 'apply_time', 'DATETIME'),
        ('bounty_projects', 'apply_err', "VARCHAR(256) DEFAULT ''"),
    ]
    try:
        from sqlalchemy import inspect, text
        insp = inspect(database.engine)
        for table, col, typedef in additions:
            if not insp.has_table(table):
                continue
            cols = {c['name'] for c in insp.get_columns(table)}
            if col not in cols:
                with database.engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {typedef}'))
    except Exception as e:
        print(f'[migrate] warning: {e}')


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(ROOT, 'templates'),
        static_folder=os.path.join(ROOT, 'static'),
    )
    app.config.from_object('config.Config')
    CORS(app)
    db.init_app(app)

    with app.app_context():
        from app import models  # noqa: F401
        db.create_all()
        _auto_migrate(db)

    from app.auth import auth_bp
    from app.api import api_bp
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(api_bp, url_prefix='/api')

    @app.route('/')
    def index():
        return render_template('login.html')

    @app.route('/dashboard')
    def dashboard():
        return render_template('dashboard.html')

    from app.scheduler import init_scheduler
    init_scheduler(app)

    return app
