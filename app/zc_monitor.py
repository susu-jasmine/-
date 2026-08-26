"""360 众测 (zhongce.360.net) 项目监控 + 自动报名。

鉴权: 360 众测使用**登录 Cookie** (非 header token), 需用户在浏览器登录后
复制完整 Cookie (如 Qs_lvt_xxx 等) 填入设置页。

接口 (逆向自前端 zhongce.360.net):
- 列表: GET /api/hacker/project/list  (query: page/pageSize)
- 报名: POST /api/hacker/project/user-join  (form-urlencoded: projectId)
- 成功: errno == 0; 未登录: 401/errno=410000; 限流: errno=400002

注意: 报名前平台要求实名认证+完善资料+签署保密协议+技术考核,
未满足时 user-join 会返回对应 errmsg, 失败原因会推送通知。
"""
from datetime import datetime, timezone
import requests
from app import db
from app.models import ZcProject

API_LIST = 'https://zhongce.360.net/api/hacker/project/list'
API_JOIN = 'https://zhongce.360.net/api/hacker/project/user-join'
DETAIL_URL_TPL = 'https://zhongce.360.net/hacker/project/detail/{id}'

MAX_PAGES = 2
PAGE_SIZE = 20

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Referer': 'https://zhongce.360.net/hacker/project/',
    'X-Requested-With': 'XMLHttpRequest',
}

# token 状态: ok | expired | unknown (expired = 未登录/401/cookie失效)
_TOKEN_OK = 'ok'
_TOKEN_EXPIRED = 'expired'

_last_health = {}  # user_id -> {'token_status':..,'last_ok_at':..,'last_err':..}


def get_health(user_id: int) -> dict:
    return _last_health.get(user_id, {
        'token_status': 'unknown', 'last_ok_at': None, 'last_err': None,
    })


def _record_health(user, token_status: str, err: str = ''):
    now_iso = datetime.now(timezone.utc).isoformat()
    prev = _last_health.get(user.id, {})
    was_expired = prev.get('token_status') == _TOKEN_EXPIRED
    _last_health[user.id] = {
        'token_status': token_status,
        'last_ok_at': now_iso if token_status == _TOKEN_OK else prev.get('last_ok_at'),
        'last_err': err or None,
    }
    return was_expired


def _handle_expired(user):
    """cookie 失效处理: 告警 + 记录。"""
    was_expired = _record_health(user, _TOKEN_EXPIRED, 'cookie 失效/未登录')
    if not was_expired:
        from app.api import notify_zc_token_expired
        notify_zc_token_expired(user)


def _headers(cookie: str) -> dict:
    h = dict(DEFAULT_HEADERS)
    h['Cookie'] = cookie
    return h


# ---------------------------------------------------------------------------
# Cookie 滑动续期: 360 可能在响应里 Set-Cookie 下发新会话,
# 必须接收并回写, 否则固定用旧 cookie 必然过期 (浏览器就是这样自动续的)。
# ---------------------------------------------------------------------------
# 进程级会话缓存: user_id -> requests.Session (带 cookie jar)
import threading

_sessions = {}
_session_lock = threading.Lock()


def _get_session(user, cookie: str):
    """取(或建)该用户的 HTTP 会话; 若 cookie 变化则重置 jar。线程安全。"""
    with _session_lock:
        sess = _sessions.get(user.id)
        jar_sig = getattr(sess, '_cookie_sig', None) if sess else None
        if sess is None or jar_sig != cookie:
            sess = requests.Session()
            sess.headers.update(DEFAULT_HEADERS)
            # 仅新建时用 DB cookie 填充 jar; 之后由 Set-Cookie 自动续期,
            # 不能反复覆盖, 否则会冲掉服务器下发的新值
            for pair in cookie.split(';'):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    sess.cookies.set(k.strip(), v.strip(), domain='zhongce.360.net')
            sess._cookie_sig = cookie
            _sessions[user.id] = sess
    return sess


def _sync_cookie_back(user, sess) -> bool:
    """把 jar 里的最新 cookie 回写到用户记录。返回是否更新。"""
    new_cookie = '; '.join(
        f'{c.name}={c.value}' for c in sess.cookies
    )
    old = (user.zc_cookie or '').strip()
    if new_cookie and new_cookie != old:
        user.zc_cookie = new_cookie
        # 同步签名, 下次 _get_session 不因签名变化重建 jar
        sess._cookie_sig = new_cookie
        try:
            from app import db
            db.session.commit()
            return True
        except Exception:
            from app import db
            db.session.rollback()
    return False


def fetch_open_projects(cookie: str, pages: int = None, user=None):
    """拉取项目列表。返回 (results, status)。status: ok|expired|error。

    传入 user 时使用 Session (自动接收 Set-Cookie 续期) 并回写最新 cookie。
    360 众测列表公开可见但需登录态; 返回字段名做宽容解析:
    - 列表可能在 data.list / data.data / data.rows / data 直接是数组
    - 项目 id: id / projectId / project_id
    """
    if not cookie:
        return [], 'expired'
    sess = _get_session(user, cookie) if user else None
    max_pages = pages or MAX_PAGES
    results = []
    for page in range(1, max_pages + 1):
        try:
            if sess:
                resp = sess.get(
                    API_LIST,
                    params={'page': page, 'pageSize': PAGE_SIZE},
                    timeout=20,
                )
                # 接收续期: Set-Cookie 自动进 jar, 回写 DB
                _sync_cookie_back(user, sess)
            else:
                resp = requests.get(
                    API_LIST,
                    params={'page': page, 'pageSize': PAGE_SIZE},
                    headers=_headers(cookie), timeout=20,
                )
        except Exception:
            return results, 'error'
        if resp.status_code == 401:
            return results, 'expired'
        if resp.status_code != 200:
            return results, 'error'
        try:
            data = resp.json()
        except Exception:
            return results, 'error'
        errno = data.get('errno')
        if errno == 410000:      # 未登录
            return results, 'expired'
        if errno == 400002:      # 请求过于频繁
            return results, 'error'
        if errno != 0 and errno is not None:
            return results, 'error'

        ret = data.get('data') or {}
        items = None
        if isinstance(ret, list):
            items = ret
        else:
            for k in ('list', 'rows', 'data', 'records', 'items'):
                if isinstance(ret.get(k), list):
                    items = ret[k]
                    break
        if items is None:
            # 容错: data 里直接嵌套对象
            items = []
        results.extend(items)
        # 分页停止: 不足一页说明到底了
        if len(items) < PAGE_SIZE:
            break
    return results, 'ok'


def _to_reward(val) -> float:
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_dt(s, fmt):
    if not s:
        return None
    try:
        return datetime.strptime(str(s), fmt)
    except (TypeError, ValueError):
        return None


def _get_id(it) -> int:
    for k in ('id', 'projectId', 'project_id'):
        v = it.get(k)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                continue
    return None


def apply_project(cookie: str, project_id: int, user=None):
    """调用报名接口。返回 (ok, errmsg, status)。status: ok|failed|expired|error。

    报名前平台有前置检查 (实名/资料/协议/考核), 失败时 errmsg 带原因。
    传入 user 时走 Session (接收 Set-Cookie 续期并回写)。
    """
    if not cookie:
        return False, '未配置 Cookie', 'expired'
    sess = _get_session(user, cookie) if user else None
    try:
        if sess:
            resp = sess.post(API_JOIN, data={'projectId': project_id}, timeout=20)
            _sync_cookie_back(user, sess)
        else:
            resp = requests.post(
                API_JOIN,
                data={'projectId': project_id},
                headers=_headers(cookie), timeout=20,
            )
    except Exception:
        return False, '网络请求异常', 'error'
    if resp.status_code == 401:
        return False, 'cookie 失效', 'expired'
    if resp.status_code != 200:
        return False, f'HTTP {resp.status_code}', 'error'
    try:
        data = resp.json()
    except Exception:
        return False, '响应解析失败', 'error'
    errno = data.get('errno')
    if errno == 410000:
        return False, data.get('errmsg') or '未登录', 'expired'
    if errno == 400002:
        return False, '请求过于频繁', 'error'
    if errno != 0:
        return False, str(data.get('errmsg') or f'errno={errno}'), 'failed'
    return True, str(data.get('errmsg') or '报名成功'), 'ok'


def scan_zc(user, light: bool = False) -> tuple:
    """扫描一次 360 众测。返回 (可报名项目总数, 本次新发现数)。

    与 scan_bountyteam 同构: upsert、自动报名、cookie 失效告警。
    """
    cookie = (user.zc_cookie or '').strip()
    if not cookie:
        _record_health(user, _TOKEN_EXPIRED, '未配置 cookie')
        return 0, 0

    items, status = fetch_open_projects(cookie, pages=1 if light else None, user=user)
    if status == 'expired':
        _handle_expired(user)
        return 0, 0
    if status == 'error':
        _record_health(user, 'unknown', '请求异常/限流')
        return 0, 0
    _record_health(user, _TOKEN_OK)

    now = datetime.now(timezone.utc)
    seen_pids = set()
    new_count = 0
    reopened = []
    apply_candidates = []

    for it in items:
        pid = _get_id(it)
        if pid is None:
            continue
        seen_pids.add(pid)
        existing = ZcProject.query.filter_by(
            user_id=user.id, project_id=pid,
        ).first()
        if existing:
            was_open = existing.is_open
            _stale = light and (
                not existing.last_seen or
                (now - existing.last_seen.replace(tzinfo=timezone.utc)).total_seconds() > 30
            )
            if not light or _stale:
                existing.last_seen = now
            existing.is_open = True
            existing.states = str(it.get('states', '') or it.get('status', '') or existing.states)
            existing.surplus = _to_reward(it.get('surplus', existing.surplus or 0))
            existing.reward_min = _to_reward(it.get('rewardMin', it.get('minReward', existing.reward_min)))
            existing.reward_max = _to_reward(it.get('rewardMax', it.get('maxReward', existing.reward_max)))
            st = it.get('startTime') or it.get('startime') or it.get('start_time')
            if st:
                dt = _parse_dt(st, '%Y-%m-%d %H:%M:%S') or _parse_dt(st, '%Y-%m-%d')
                if dt:
                    existing.startime = dt
            if not was_open:
                reopened.append(existing.name)
                apply_candidates.append(existing)
        else:
            st = it.get('startTime') or it.get('startime') or it.get('start_time')
            dt = _parse_dt(st, '%Y-%m-%d %H:%M:%S') or _parse_dt(st, '%Y-%m-%d')
            proj = ZcProject(
                user_id=user.id,
                project_id=pid,
                name=str(it.get('name') or it.get('title') or it.get('projectName') or ''),
                project_type=str(it.get('projectType', it.get('type', ''))),
                states=str(it.get('states', it.get('status', ''))),
                startime=dt,
                surplus=_to_reward(it.get('surplus')),
                reward_min=_to_reward(it.get('rewardMin', it.get('minReward'))),
                reward_max=_to_reward(it.get('rewardMax', it.get('maxReward'))),
                detail_url=DETAIL_URL_TPL.format(id=pid),
                first_seen=now,
                last_seen=now,
                is_new=True,
                is_open=True,
            )
            db.session.add(proj)
            new_count += 1
            apply_candidates.append(proj)

    # 关闭检测 (报名成功/名额满/结束 → 移出列表)
    open_rows = (
        ZcProject.query
        .filter(
            ZcProject.user_id == user.id,
            ZcProject.is_open == True,  # noqa: E712
        )
        .all()
    )
    closed_names = []
    applied_gone = []
    for row in open_rows:
        if row.project_id not in seen_pids:
            row.is_open = False
            if row.apply_status == 'applied':
                applied_gone.append(row.name)
            else:
                closed_names.append(row.name)

    _changed = bool(new_count or closed_names or reopened or applied_gone)
    if light and not _changed:
        db.session.rollback()
    else:
        db.session.commit()

    # ---- 自动报名 (新发现 + 重新开放 + 失败到期重试) ----
    applied_ok, applied_fail = [], []
    if apply_candidates and user.zc_auto_apply:
        _seen = set()
        candidates = []
        for p in apply_candidates:
            if p.project_id not in _seen:
                _seen.add(p.project_id)
                candidates.append(p)
        # 失败重试: 10 分钟节流
        retry_after = 600
        _now_naive = now.replace(tzinfo=None)
        failed_rows = (
            ZcProject.query
            .filter(
                ZcProject.user_id == user.id,
                ZcProject.is_open == True,  # noqa: E712
                ZcProject.apply_status == 'failed',
            )
            .all()
        )
        for row in failed_rows:
            if row.project_id in seen_pids:
                continue
            if row.apply_time and (_now_naive - row.apply_time).total_seconds() >= retry_after:
                candidates.append(row)
                row.is_open = True

        now_t = datetime.now(timezone.utc)
        from concurrent.futures import ThreadPoolExecutor

        def _do_apply(p):
            return p.project_id, apply_project(cookie, p.project_id, user=user)

        expired_hit = False
        with ThreadPoolExecutor(max_workers=min(5, len(candidates) or 1)) as ex:
            for pid, (ok, msg, st) in ex.map(_do_apply, candidates):
                p = next(x for x in candidates if x.project_id == pid)
                p.apply_status = 'applied' if ok else 'failed'
                p.apply_time = now_t
                p.apply_err = '' if ok else msg[:256]
                if ok:
                    applied_ok.append((p.name, msg))
                else:
                    applied_fail.append((p.name, msg))
                if st == 'expired':
                    expired_hit = True
        if expired_hit:
            _handle_expired(user)
        db.session.commit()

    # ---- 通知 ----
    if new_count > 0:
        from app.api import notify_zc_new
        fresh = (
            ZcProject.query
            .filter_by(user_id=user.id, is_new=True, is_open=True)
            .order_by(ZcProject.first_seen.desc())
            .limit(new_count)
            .all()
        )
        notify_zc_new(
            user, [p.name for p in fresh],
            [(p.name, p.reward_min, p.reward_max, p.apply_status, p.apply_err) for p in fresh],
        )
    if applied_ok or applied_fail:
        from app.api import notify_zc_apply_result
        notify_zc_apply_result(user, applied_ok, applied_fail)
    if closed_names:
        from app.api import notify_zc_closed
        notify_zc_closed(user, closed_names)
    if reopened:
        from app.api import notify_zc_reopen
        notify_zc_reopen(user, reopened)

    return len(items), new_count
