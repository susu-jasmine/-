from datetime import datetime, timezone
from app import db


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    email = db.Column(db.String(128), default='')
    pushplus_token = db.Column(db.String(64), default='')
    smtp_host = db.Column(db.String(128), default='')
    smtp_port = db.Column(db.Integer, default=587)
    smtp_user = db.Column(db.String(128), default='')
    smtp_pass = db.Column(db.String(256), default='')
    smtp_from = db.Column(db.String(128), default='')
    notify_email = db.Column(db.Boolean, default=False)
    notify_wechat = db.Column(db.Boolean, default=True)
    src_interval_hours = db.Column(db.Integer, default=1)
    # --- BountyTeam (雷神众测) ---
    bountyteam_token = db.Column(db.String(128), default='')
    bountyteam_interval_minutes = db.Column(db.Integer, default=3)
    # 自动报名开关: 检测到新的可报名项目时立即调用平台报名接口 (默认关闭)
    bountyteam_auto_apply = db.Column(db.Boolean, default=False)
    # 极速模式: 秒级轮询守护线程 (默认关闭), 开启后取代分钟级定时扫描
    bountyteam_fast_poll = db.Column(db.Boolean, default=False)
    # 轮询间隔秒数 (1-60, 极速模式下生效; 受平台风控约束不建议低于 1s)
    bountyteam_poll_seconds = db.Column(db.Integer, default=3)
    # --- 360 众测 (zhongce.360.net) ---
    zc_cookie = db.Column(db.String(2048), default='')       # 登录 cookie (完整)
    zc_interval_seconds = db.Column(db.Integer, default=3)   # 秒级轮询间隔
    zc_auto_apply = db.Column(db.Boolean, default=False)     # 自动报名
    zc_fast_poll = db.Column(db.Boolean, default=False)      # 启用秒级轮询
    # --- 补天/漏洞盒子 秒级轮询间隔 (秒) ---
    src_poll_seconds = db.Column(db.Integer, default=5)
    src_fast_poll = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    domains = db.relationship(
        'Domain', backref='owner', lazy='dynamic', cascade='all, delete-orphan'
    )


class Domain(db.Model):
    __tablename__ = 'domains'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    domain = db.Column(db.String(256), nullable=False)
    status = db.Column(db.String(16), default='active')  # active | paused
    organization = db.Column(db.String(128), default='', index=True)
    interval_hours = db.Column(db.Integer, default=6)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_scan_at = db.Column(db.DateTime, nullable=True)

    assets = db.relationship(
        'Asset', backref='domain', lazy='dynamic', cascade='all, delete-orphan'
    )
    scan_logs = db.relationship(
        'ScanLog', backref='domain', lazy='dynamic', cascade='all, delete-orphan'
    )

    __table_args__ = (db.UniqueConstraint('user_id', 'domain', name='uq_user_domain'),)


class Asset(db.Model):
    __tablename__ = 'assets'

    id = db.Column(db.Integer, primary_key=True)
    domain_id = db.Column(db.Integer, db.ForeignKey('domains.id'), nullable=False)
    subdomain = db.Column(db.String(512), nullable=False)
    ip_addresses = db.Column(db.Text, default='')
    source = db.Column(db.String(64), default='')
    first_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_new = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint('domain_id', 'subdomain', name='uq_domain_sub'),
    )


class SrcProgram(db.Model):
    __tablename__ = 'src_programs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    platform = db.Column(db.String(32), nullable=False)
    tab = db.Column(db.String(32), default='')
    company_id = db.Column(db.String(64), nullable=False)
    company_name = db.Column(db.String(256), nullable=False)
    reward_min = db.Column(db.Integer, default=0)
    reward_max = db.Column(db.Integer, default=0)
    description = db.Column(db.Text, default='')
    change_time = db.Column(db.DateTime, nullable=True)
    recommend = db.Column(db.Boolean, default=False)
    service_status = db.Column(db.String(32), default='')
    first_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_new = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'platform', 'company_id', name='uq_user_platform_company'),
    )


class ScanLog(db.Model):
    __tablename__ = 'scan_logs'

    id = db.Column(db.Integer, primary_key=True)
    domain_id = db.Column(db.Integer, db.ForeignKey('domains.id'), nullable=False)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = db.Column(db.DateTime, nullable=True)
    assets_found = db.Column(db.Integer, default=0)
    new_assets_found = db.Column(db.Integer, default=0)
    status = db.Column(db.String(16), default='running')  # running | completed | failed


class BountyProject(db.Model):
    """雷神众测 (bountyteam.com) 项目 — 仅记录"未报名 + 有剩余名额"的项目。"""
    __tablename__ = 'bounty_projects'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    project_id = db.Column(db.Integer, nullable=False)          # 接口返回的 id
    name = db.Column(db.String(256), nullable=False)            # 项目名
    project_type = db.Column(db.String(32), default='')         # bugbounty | SecurityResponse
    states = db.Column(db.String(16), default='')               # apply | doing | pause | stop
    startime = db.Column(db.DateTime, nullable=True)            # 开始时间
    surplus = db.Column(db.Integer, default=0)                  # 剩余天数
    remainder_num = db.Column(db.String(32), default='')        # 剩余名额原始字符串 "4人" / "不限人数"
    reward_min = db.Column(db.Float, default=0)                 # lowriskreward
    reward_max = db.Column(db.Float, default=0)                 # highriskreward
    detail_url = db.Column(db.String(256), default='')
    first_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_new = db.Column(db.Boolean, default=True)
    # 项目一旦被报名/名额满/结束,扫描器会把它标记为 closed,前端默认不展示
    is_open = db.Column(db.Boolean, default=True)
    # --- 自动报名状态: '' 未尝试 | applied 已报名 | failed 报名失败 ---
    apply_status = db.Column(db.String(16), default='')
    apply_time = db.Column(db.DateTime, nullable=True)
    apply_err = db.Column(db.String(256), default='')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'project_id', name='uq_user_bounty_project'),
    )


class ZcProject(db.Model):
    """360 众测 (zhongce.360.net) 项目 — 仅记录"可报名"的项目。"""
    __tablename__ = 'zc_projects'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    project_id = db.Column(db.Integer, nullable=False)          # 接口返回的 id
    name = db.Column(db.String(256), nullable=False)            # 项目名
    project_type = db.Column(db.String(32), default='')         # 项目类型
    states = db.Column(db.String(16), default='')               # 状态
    startime = db.Column(db.DateTime, nullable=True)            # 开始时间
    surplus = db.Column(db.Integer, default=0)                  # 剩余天数
    reward_min = db.Column(db.Float, default=0)                 # 最低奖金
    reward_max = db.Column(db.Float, default=0)                 # 最高奖金
    detail_url = db.Column(db.String(256), default='')
    first_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_new = db.Column(db.Boolean, default=True)
    # 项目一旦被报名/名额满/结束,扫描器会把它标记为 closed,前端默认不展示
    is_open = db.Column(db.Boolean, default=True)
    # --- 自动报名状态: '' 未尝试 | applied 已报名 | failed 报名失败 ---
    apply_status = db.Column(db.String(16), default='')
    apply_time = db.Column(db.DateTime, nullable=True)
    apply_err = db.Column(db.String(256), default='')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'project_id', name='uq_user_zc_project'),
    )
