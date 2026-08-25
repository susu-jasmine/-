import os

basedir = os.path.abspath(os.path.dirname(__file__))


def _sqlite_uri():
    """构造 SQLite URI 并自动启用 WAL 模式 + 写超时，避免并发写锁报错。

    - WAL 模式: 读写不互斥，APScheduler 线程扫描入库与 Web 请求可并发。
    - busy_timeout: 写锁竞争时等待而不是立即抛 database is locked。
    - check_same_thread=False: 允许跨线程使用连接 (SQLAlchemy 会话池需要)。
    """
    default_path = os.path.join(basedir, 'data', 'monitor.db')
    db_path = os.environ.get('DATABASE_URL', f'sqlite:///{default_path}')
    # 用户传的是文件路径而非 sqlite:/// URI 时，规范化一下
    if not db_path.startswith('sqlite:'):
        db_path = f'sqlite:///{db_path}'
    # 已带连接参数的不重复追加
    if '?' in db_path:
        return db_path
    sep = '&' if '?' in db_path else '?'
    return (
        f'{db_path}{sep}timeout=30'
        '&check_same_thread=False'
    )


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(32).hex())
    SQLALCHEMY_DATABASE_URI = _sqlite_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 单进程多线程 (Gunicorn sync worker + APScheduler) 下避免连接泄漏
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}

    JWT_EXPIRATION_HOURS = int(os.environ.get('JWT_EXPIRATION_HOURS', '24'))
    DEFAULT_SCAN_INTERVAL = int(os.environ.get('DEFAULT_SCAN_INTERVAL', '6'))
    SCAN_TIMEOUT = int(os.environ.get('SCAN_TIMEOUT', '30'))

    LOGIN_MAX_ATTEMPTS = int(os.environ.get('LOGIN_MAX_ATTEMPTS', '5'))
    LOGIN_LOCKOUT_MINUTES = int(os.environ.get('LOGIN_LOCKOUT_MINUTES', '15'))
