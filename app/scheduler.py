from apscheduler.schedulers.background import BackgroundScheduler
from app import db
from app.models import Domain, User

scheduler: BackgroundScheduler = None
_app_ref = None


def init_scheduler(app):
    global scheduler, _app_ref
    _app_ref = app

    scheduler = BackgroundScheduler()
    scheduler.start()

    with app.app_context():
        for d in Domain.query.filter_by(status='active').all():
            _add_job(d)

    # SRC platform scan with configurable interval
    _schedule_src_scan(app)

    # BountyTeam (雷神众测) 高频监控 — 分钟级
    _schedule_bountyteam_scan(app)
    # 独立保活心跳: 防止长时间无活动导致 token 过期 (滑动续期)
    _schedule_bountyteam_keepalive(app)
    # 极速模式 (秒级守护线程): 若有用户开启则取代分钟级 job
    from app.bountyteam_monitor import any_fast_poll_enabled, start_fast_poll
    with app.app_context():
        if any_fast_poll_enabled():
            if scheduler.get_job('bountyteam_scan'):
                scheduler.remove_job('bountyteam_scan')
            start_fast_poll(app)
    import threading
    def _delayed_first_bt():
        import time
        time.sleep(15)
        with app.app_context():
            _bountyteam_scan_wrapper()
    threading.Thread(target=_delayed_first_bt, daemon=True).start()

    # Run initial SRC scan 8s after startup
    import threading
    def _delayed_first_scan():
        import time
        time.sleep(8)
        with app.app_context():
            _src_scan_wrapper()
    threading.Thread(target=_delayed_first_scan, daemon=True).start()


def _add_job(domain_obj):
    jid = f'scan_{domain_obj.id}'
    if scheduler.get_job(jid):
        scheduler.remove_job(jid)
    scheduler.add_job(
        _scan_wrapper,
        trigger='interval',
        hours=domain_obj.interval_hours,
        id=jid,
        args=[domain_obj.id],
        replace_existing=True,
    )


def _scan_wrapper(domain_id: int):
    with _app_ref.app_context():
        from app.scanner import scan_domain
        from app.notifier import notify_new_assets
        from app.models import Asset

        d = db.session.get(Domain, domain_id)
        if not d or d.status != 'active':
            return

        new_count, _ = scan_domain(d)

        if new_count > 0:
            new_assets = (
                Asset.query.filter_by(domain_id=domain_id, is_new=True)
                .order_by(Asset.first_seen.desc())
                .limit(new_count)
                .all()
            )
            notify_new_assets(d.owner, d.domain, [a.subdomain for a in new_assets])


def add_domain_job(domain_obj):
    _add_job(domain_obj)


def remove_domain_job(domain_id: int):
    jid = f'scan_{domain_id}'
    if scheduler and scheduler.get_job(jid):
        scheduler.remove_job(jid)


def pause_domain_job(domain_id: int):
    jid = f'scan_{domain_id}'
    if scheduler and scheduler.get_job(jid):
        scheduler.pause_job(jid)


def _src_scan_wrapper():
    with _app_ref.app_context():
        from app.src_monitor import scan_src_platforms
        from app.models import SrcProgram
        users = User.query.all()
        for u in users:
            try:
                total, new_count = scan_src_platforms(u)
                print(f'[SRC] user={u.username} total={total} new={new_count}')
                if new_count > 0:
                    from app.api import _notify_new_src
                    new_programs = (
                        SrcProgram.query.filter_by(user_id=u.id, is_new=True)
                        .order_by(SrcProgram.first_seen.desc())
                        .limit(new_count)
                        .all()
                    )
                    _notify_new_src(u, [p.company_name for p in new_programs], new_count)
            except Exception as e:
                print(f'[SRC] scan error for {u.username}: {e}')


def _schedule_src_scan(app):
    """Read user-configured interval and schedule SRC scan job."""
    with app.app_context():
        users = User.query.all()
        interval = 1  # default
        if users:
            interval = max(1, min(u.src_interval_hours for u in users if u.src_interval_hours))
    scheduler.add_job(
        _src_scan_wrapper,
        trigger='interval',
        hours=interval,
        id='src_platform_scan',
        replace_existing=True,
    )

def reschedule_src_scan():
    """Called after user updates their SRC interval setting."""
    if scheduler and _app_ref:
        _schedule_src_scan(_app_ref)

def resume_domain_job(domain_id: int):
    jid = f'scan_{domain_id}'
    if scheduler and scheduler.get_job(jid):
        scheduler.resume_job(jid)


# ---------------------------------------------------------------------------
# BountyTeam (雷神众测) 高频监控调度
# ---------------------------------------------------------------------------
def _bountyteam_scan_wrapper():
    """扫描所有配置了 token 的用户的雷神众测项目。"""
    with _app_ref.app_context():
        from app.bountyteam_monitor import scan_bountyteam
        users = User.query.all()
        for u in users:
            if not (u.bountyteam_token or '').strip():
                continue
            try:
                total, new_count = scan_bountyteam(u)
                print(f'[BountyTeam] user={u.username} open={total} new={new_count}')
            except Exception as e:
                print(f'[BountyTeam] scan error for {u.username}: {e}')


def _schedule_bountyteam_scan(app):
    """读取用户配置的分钟级间隔, 注册定时任务。"""
    with app.app_context():
        users = User.query.all()
        interval = 3  # 默认 3 分钟
        configured = [u.bountyteam_interval_minutes for u in users
                      if u.bountyteam_interval_minutes and u.bountyteam_token]
        if configured:
            # 取最小值, 保证最敏感的用户能及时收到
            interval = max(1, min(configured))
    if scheduler.get_job('bountyteam_scan'):
        scheduler.remove_job('bountyteam_scan')
    scheduler.add_job(
        _bountyteam_scan_wrapper,
        trigger='interval',
        minutes=interval,
        id='bountyteam_scan',
        replace_existing=True,
    )


def reschedule_bountyteam_scan():
    """用户修改 token / 间隔 / 极速模式后调用。

    极速模式开: 停分钟级 job, 起秒级守护线程。
    极速模式关: 停守护线程, 恢复分钟级 job。
    """
    if not (scheduler and _app_ref):
        return
    from app.bountyteam_monitor import (
        any_fast_poll_enabled, start_fast_poll, stop_fast_poll,
    )
    with _app_ref.app_context():
        fast = any_fast_poll_enabled()
    if fast:
        if scheduler.get_job('bountyteam_scan'):
            scheduler.remove_job('bountyteam_scan')
        start_fast_poll(_app_ref)
    else:
        stop_fast_poll()
        _schedule_bountyteam_scan(_app_ref)


def _bountyteam_keepalive_wrapper():
    """保活心跳: 对所有配了 token 的用户各发一次轻请求, 触发站点滑动续期。"""
    with _app_ref.app_context():
        from app.bountyteam_monitor import keepalive_bountyteam
        users = User.query.all()
        for u in users:
            if not (u.bountyteam_token or '').strip():
                continue
            try:
                keepalive_bountyteam(u)
            except Exception as e:
                print(f'[BountyTeam-keepalive] error for {u.username}: {e}')


def _schedule_bountyteam_keepalive(app):
    """注册保活心跳 job (固定 30 分钟一次, 不随用户间隔变化)。"""
    from app.bountyteam_monitor import KEEPALIVE_MINUTES
    if scheduler.get_job('bountyteam_keepalive'):
        scheduler.remove_job('bountyteam_keepalive')
    scheduler.add_job(
        _bountyteam_keepalive_wrapper,
        trigger='interval',
        minutes=KEEPALIVE_MINUTES,
        id='bountyteam_keepalive',
        replace_existing=True,
    )
