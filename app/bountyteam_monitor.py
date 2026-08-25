"""雷神众测 (bountyteam.com) 项目监控。

监控目标: 最新、未报名、且仍有剩余名额的可信众测项目。
- 接口: GET https://www.bountyteam.com/web/v1/project/getProjectList
- 鉴权: Authorization: <jwtToken>  (用户在 bountyteam 站点登录后 localStorage 里的 UUID)
- 筛选参数: joinStatus=unApply (未报名), lastPush=1 (最新优先)

"有剩余名额" 判定: remainder_num 解析出的数字 > 0, 或为 "不限人数"。

## Token 24h 保活机制
bountyteam 登录强制图形验证码 + 邮箱/短信验证码, 无法用账号密码自动重登。
但站点有"滑动续期": 只要 token 还有效, 每次 API 响应里若带 ret.token 就会下发新 token。
因此采用:
  1) 每次扫描/心跳请求后, 若响应 ret.token 有值 → 自动更新入库 (续命)。
  2) 独立保活心跳 job (默认 30 分钟一次) 无条件请求, 防止长时间无活动导致过期。
  3) 一旦接口返回 errcode=401 → token 已彻底失效, 推送告警提醒人工换 token,
     并记录 token_status='expired', 前端可见。
"""
import re
from datetime import datetime, timezone
import requests
from app import db
from app.models import BountyProject, User

API_URL = 'https://www.bountyteam.com/web/v1/project/getProjectList'
DETAIL_URL_TPL = 'https://www.bountyteam.com/hacker-service/bugBounty-deatil/{id}'
# 报名接口 (前端 signProject: GET /web/v1/project/hacker/signProject?id=xxx)
APPLY_URL = 'https://www.bountyteam.com/web/v1/project/hacker/signProject'

# 只拉前 N 页就够覆盖最新可报名项目(每页 size 条)
MAX_PAGES = 3
PAGE_SIZE = 20

# 保活心跳间隔(分钟)。token 过期窗口约 8h, 30 分钟足够安全。
KEEPALIVE_MINUTES = 30

_NUM_RE = re.compile(r'-?\d+')

# token 状态: ok | expired | unknown
_TOKEN_OK = 'ok'
_TOKEN_EXPIRED = 'expired'


def _parse_remainder(raw) -> tuple:
    """解析 remainderNum 字段。返回 (剩余名额整数或None, 是否不限人数)。"""
    if raw is None:
        return None, False
    s = str(raw).strip()
    if '不限' in s:
        return None, True
    m = _NUM_RE.search(s)
    if not m:
        return None, False
    try:
        return int(m.group()), False
    except ValueError:
        return None, False


def _has_quota(raw) -> bool:
    """是否还有剩余名额。"""
    num, unlimited = _parse_remainder(raw)
    return unlimited or (num is not None and num > 0)


def _extract_new_token(data) -> str:
    """从响应里提取续期 token (站点滑动续期: ret.token)。"""
    try:
        ret = (data or {}).get('ret') or {}
        tok = ret.get('token')
        if tok and isinstance(tok, str) and tok != 'null':
            return tok.strip()
    except Exception:
        pass
    return ''


def _api_get(token: str, params: dict):
    """发一次请求。返回 (data_dict, new_token, status)。
    status: 'ok' | 'expired' | 'error'
    """
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json',
        'Authorization': token,
        'Referer': 'https://www.bountyteam.com/hacker-service/bug-bounty-list',
    }
    try:
        resp = requests.get(API_URL, params=params, headers=headers, timeout=20)
    except Exception:
        return None, '', 'error'
    if resp.status_code != 200:
        return None, '', 'error'
    try:
        data = resp.json()
    except Exception:
        return None, '', 'error'
    # 401 = token 失效
    if data.get('errcode') == 401:
        return data, '', 'expired'
    if data.get('errcode') != 0:
        return data, '', 'error'
    return data, _extract_new_token(data), 'ok'


def apply_project(token: str, project_id: int):
    """调用平台报名接口。返回 (ok, errmsg, new_token, status)。

    前端逻辑: signProject({id}) → errcode==0 即报名成功, errmsg 为提示文本。
    """
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json',
        'Authorization': token,
        'Referer': DETAIL_URL_TPL.format(id=project_id),
    }
    try:
        resp = requests.get(
            APPLY_URL, params={'id': project_id},
            headers=headers, timeout=20,
        )
    except Exception:
        return False, '网络请求异常', '', 'error'
    if resp.status_code != 200:
        return False, f'HTTP {resp.status_code}', '', 'error'
    try:
        data = resp.json()
    except Exception:
        return False, '响应解析失败', '', 'error'
    new_tok = _extract_new_token(data)
    if data.get('errcode') == 401:
        return False, data.get('errmsg') or 'token 失效', new_tok, 'expired'
    if data.get('errcode') != 0:
        # 常见失败: 请先实名认证 / 名额已满 / 已报名过 等, errmsg 带原因
        return False, str(data.get('errmsg') or f'errcode={data.get("errcode")}'), new_tok, 'failed'
    return True, str(data.get('errmsg') or '报名成功'), new_tok, 'ok'


def fetch_open_projects(token: str, pages: int = None):
    """拉取所有"未报名 + 最新"项目, 再本地过滤出"有剩余名额 且 非 stop"的。

    返回 (results, new_token, status)。
    pages: 极速轮询传 1 只拉首页(最新项目都在首页), 降低单轮请求量。
    遇到第一个全页都没有可报名项目的页就提前停止(接口按最新优先排序,
    说明后续都是历史项目)。
    """
    if not token:
        return [], '', 'expired'

    max_pages = pages or MAX_PAGES
    results = []
    new_token_acc = ''
    empty_streak = 0
    for page in range(1, max_pages + 1):
        data, new_tok, status = _api_get(token, {
            'page': page, 'size': PAGE_SIZE,
            'lastPush': 1, 'joinStatus': 'unApply',
        })
        if status == 'expired':
            return results, '', 'expired'
        if status == 'error':
            break
        if new_tok:
            new_token_acc = new_tok

        items = (data.get('ret') or {}).get('data') or []

        page_hits = []
        for it in items:
            if it.get('states') == 'stop':
                continue
            if not _has_quota(it.get('remainderNum')):
                continue
            page_hits.append(it)

        if page_hits:
            results.extend(page_hits)
            empty_streak = 0
        else:
            empty_streak += 1
            if empty_streak >= 1:
                # 当前页全是已满/已结束, 后面更老的页基本也不会有了
                break
    return results, new_token_acc, 'ok'


def _set_token_status(user, status: str):
    """把 token 健康状态记到 User (复用 bountyteam_interval_minutes 旁无字段,
    临时记到一个模块级缓存 + DB 字段 bounty_token_status)。"""
    # 健康状态主要靠前端轮询 /api/bounty/stats 实时返回, 这里只触发告警。
    pass


def _to_reward(val) -> float:
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_dt(s, fmt):
    if not s:
        return None
    try:
        return datetime.strptime(s, fmt)
    except (TypeError, ValueError):
        return None


# 上次扫描的健康状态缓存 (进程级), 供 stats API 读取
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
    """token 失效处理: 告警 + 记录。"""
    was_expired = _record_health(user, _TOKEN_EXPIRED, '401 权限鉴定失败')
    if not was_expired:
        # 仅在"从有效→失效"的边沿推一次, 避免每次扫描都刷屏
        from app.api import notify_bountyteam_token_expired
        notify_bountyteam_token_expired(user)


def scan_bountyteam(user, light: bool = False) -> tuple:
    """扫描一次。返回 (可报名项目总数, 本次新发现数)。

    - 把当前仍可报名的项目 upsert 进库 (is_open=True), 新出现的 is_new=True。
    - 响应里的续期 token 自动回写入库 (滑动续期保活)。
    - token 失效(401)时记录健康状态并告警, 不再做无效重试。
    - light=True: 极速轮询路径 — 只拉首页、无变化不写库、last_seen 节流刷新。
    """
    token = (user.bountyteam_token or '').strip()
    if not token:
        _record_health(user, _TOKEN_EXPIRED, '未配置 token')
        return 0, 0

    items, new_token, status = fetch_open_projects(token, pages=1 if light else None)

    # 续期: 回写新 token
    if new_token and new_token != token:
        user.bountyteam_token = new_token
        db.session.commit()

    if status == 'expired':
        _handle_expired(user)
        return 0, 0
    if status == 'error':
        _record_health(user, 'unknown', '请求异常')
        return 0, 0

    # 请求成功 → 健康状态 ok
    _record_health(user, _TOKEN_OK)

    now = datetime.now(timezone.utc)
    seen_pids = set()
    new_count = 0
    reopened = []   # 之前关闭、本次又重新有余量的项目名(可重新报名)
    # 本轮需要报名的候选 (新发现 + 重新开放 + 失败到期重试), 均为 ORM 对象
    apply_candidates = []

    for it in items:
        pid = it.get('id')
        if pid is None:
            continue
        seen_pids.add(pid)

        existing = BountyProject.query.filter_by(
            user_id=user.id, project_id=pid,
        ).first()

        if existing:
            was_open = existing.is_open
            # light 模式节流: 无变化时 30s 才刷新一次 last_seen, 减少写放大
            _stale = light and (
                not existing.last_seen or
                (now - existing.last_seen.replace(tzinfo=timezone.utc)).total_seconds() > 30
            )
            if not light or _stale:
                existing.last_seen = now
            existing.is_open = True
            existing.states = it.get('states', '') or existing.states
            existing.remainder_num = str(it.get('remainderNum', '') or '')
            existing.surplus = it.get('surplus', existing.surplus or 0)
            existing.reward_min = _to_reward(it.get('lowriskreward'))
            existing.reward_max = _to_reward(it.get('highriskreward'))
            existing.startime = _parse_dt(it.get('startime'), '%Y-%m-%d %H:%M:%S') or existing.startime
            if not was_open:
                reopened.append(existing.name)
                # 重新开放 = 重新可报名, 加入自动报名候选
                apply_candidates.append(existing)
        else:
            proj = BountyProject(
                user_id=user.id,
                project_id=pid,
                name=it.get('name', ''),
                project_type=it.get('projectype', ''),
                states=it.get('states', ''),
                startime=_parse_dt(it.get('startime'), '%Y-%m-%d %H:%M:%S'),
                surplus=it.get('surplus', 0) or 0,
                remainder_num=str(it.get('remainderNum', '') or ''),
                reward_min=_to_reward(it.get('lowriskreward')),
                reward_max=_to_reward(it.get('highriskreward')),
                detail_url=DETAIL_URL_TPL.format(id=pid),
                first_seen=now,
                last_seen=now,
                is_new=True,
                is_open=True,
            )
            db.session.add(proj)
            new_count += 1
            apply_candidates.append(proj)

    # 报名失败的项目: 到期后自动重试 (默认 10 分钟), 避免手动盯
    if user.bountyteam_auto_apply:
        retry_after = 600  # 秒
        _now_naive = now.replace(tzinfo=None)
        failed_rows = (
            BountyProject.query
            .filter(
                BountyProject.user_id == user.id,
                BountyProject.is_open == True,  # noqa: E712
                BountyProject.apply_status == 'failed',
            )
            .all()
        )
        for row in failed_rows:
            if row.project_id in seen_pids:
                continue  # 本轮回购的项目已在上面候选里
            if row.apply_time and (_now_naive - row.apply_time).total_seconds() >= retry_after:
                apply_candidates.append(row)
                row.is_open = True

    # 关闭: 本次没出现且原本 is_open 的项目
    # (报名成功后项目不再出现在 unApply 列表里, 会走到这里 — 需与"名额没了"区分)
    open_rows = (
        BountyProject.query
        .filter(
            BountyProject.user_id == user.id,
            BountyProject.is_open == True,  # noqa: E712
        )
        .all()
    )
    closed_names = []
    applied_gone = []   # 已自动报名、本次从列表消失(= 平台确认报名生效)的项目
    for row in open_rows:
        if row.project_id not in seen_pids:
            row.is_open = False
            if row.apply_status == 'applied':
                applied_gone.append(row.name)
            else:
                closed_names.append(row.name)

    # light 模式且本轮无任何变化 → 放弃事务, 避免秒级轮询造成写放大
    _changed = bool(new_count or closed_names or reopened or applied_gone)
    if light and not _changed:
        db.session.rollback()
    else:
        db.session.commit()

    # ---- 自动报名: 对所有候选 (新发现 + 重新开放 + 失败到期重试) 并发报名 ----
    applied_ok, applied_fail = [], []
    if apply_candidates and user.bountyteam_auto_apply:
        # 去重 (同一项目可能既被新发现又在失败重试列表)
        _seen = set()
        candidates = []
        for p in apply_candidates:
            if p.project_id not in _seen:
                _seen.add(p.project_id)
                candidates.append(p)
        now_t = datetime.now(timezone.utc)

        def _do_apply(p):
            # 并发线程内只做 HTTP 请求, DB 写回主线程 (session 非线程安全)
            return p.project_id, apply_project(token, p.project_id)

        from concurrent.futures import ThreadPoolExecutor
        expired_hit = False
        with ThreadPoolExecutor(max_workers=min(5, len(candidates) or 1)) as ex:
            for pid, (ok, msg, new_tok2, st) in ex.map(_do_apply, candidates):
                p = next(x for x in candidates if x.project_id == pid)
                if new_tok2 and new_tok2 != token:
                    token = new_tok2
                    user.bountyteam_token = new_tok2
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

    # ---- 触发告警 ----
    if new_count > 0:
        from app.api import notify_bountyteam_new
        fresh = (
            BountyProject.query
            .filter_by(user_id=user.id, is_new=True, is_open=True)
            .order_by(BountyProject.first_seen.desc())
            .limit(new_count)
            .all()
        )
        notify_bountyteam_new(
            user, [p.name for p in fresh],
            [(p.name, p.remainder_num, p.reward_min, p.reward_max,
              p.apply_status, p.apply_err) for p in fresh],
            kind='new',
        )
    # 自动报名的结果反馈 (含重新开放/失败重试的报名结果)
    if applied_ok or applied_fail:
        from app.api import notify_bountyteam_apply_result
        notify_bountyteam_apply_result(user, applied_ok, applied_fail)
    if applied_gone:
        # 报名生效确认(平台已把项目移出未报名列表)
        pass
    if closed_names:
        from app.api import notify_bountyteam_closed
        notify_bountyteam_closed(user, closed_names)
    if reopened:
        from app.api import notify_bountyteam_reopen
        notify_bountyteam_reopen(user, reopened)

    return len(items), new_count


def keepalive_bountyteam(user):
    """保活心跳: 仅发一次请求触发站点滑动续期, 不处理项目数据。

    用于长时间没有扫描活动时, 确保 token 不会因闲置过期。
    """
    token = (user.bountyteam_token or '').strip()
    if not token:
        _record_health(user, _TOKEN_EXPIRED, '未配置 token')
        return
    data, new_tok, status = _api_get(token, {
        'page': 1, 'size': 1, 'lastPush': 1, 'joinStatus': 'unApply',
    })
    if new_tok and new_tok != token:
        user.bountyteam_token = new_tok
        db.session.commit()
    if status == 'expired':
        _handle_expired(user)
    elif status == 'ok':
        _record_health(user, _TOKEN_OK)
    else:
        _record_health(user, 'unknown', '心跳请求异常')


# ---------------------------------------------------------------------------
# 极速轮询守护线程 (秒级监控 + 检测到立即报名)
# ---------------------------------------------------------------------------
import threading

# 线程状态: health 里也暴露给 stats API
_fast_state = {
    'thread': None,
    'stop': threading.Event(),
    'running': False,
    'last_poll_at': None,      # 上次轮询完成时间 (ISO)
    'poll_count': 0,           # 累计轮询次数
    'avg_latency_ms': None,    # 最近一轮 检测+报名 端到端耗时
}

# 各平台最小轮询间隔 (秒), 避免全部平台按同一个最小间隔跑
# 物理下限: 单次 HTTP 往返 ~0.3-0.7s, 轮询间隔再小也受此限制; 过低只会触发风控
PLATFORM_MIN_SECONDS = {
    'bountyteam': 0.2,
    'zc': 0.5,
    'src': 2,
}


def fast_poll_status() -> dict:
    return {
        'running': _fast_state['running'],
        'last_poll_at': _fast_state['last_poll_at'],
        'poll_count': _fast_state['poll_count'],
        'avg_latency_ms': _fast_state['avg_latency_ms'],
    }


def _get_poll_seconds(app) -> float:
    """读取所有用户里配置的最小轮询间隔 (秒)。"""
    with app.app_context():
        vals = [u.bountyteam_poll_seconds for u in User.query.all()
                if u.bountyteam_fast_poll and u.bountyteam_token
                and u.bountyteam_poll_seconds]
        return max(0.2, min(vals)) if vals else 3.0


def _fast_poll_loop(app):
    """统一多平台极速轮询主循环: 检测 → (新项目时)立即报名 → 休眠(带抖动)。

    覆盖: 雷神众测 / 360众测 / 补天+漏洞盒子(SRC)。
    - 各平台按各自的启用状态与间隔独立节流。
    - 间隔抖动 ±20%, 避免固定节奏被风控识别。
    - 连续异常时指数退避 (1s→2s→4s... 上限 60s), 429/限流自动降速。
    """
    import time, random
    _fast_state['running'] = True
    backoff = 1.0
    last_scan = {}   # ('platform', user_id) -> 上次扫描时刻
    try:
        while not _fast_state['stop'].is_set():
            t0 = time.monotonic()
            err = False
            try:
                with app.app_context():
                    users = User.query.all()
                    for u in users:
                        # ---- 雷神众测 ----
                        if u.bountyteam_fast_poll and (u.bountyteam_token or '').strip():
                            key = ('bt', u.id)
                            iv = max(PLATFORM_MIN_SECONDS['bountyteam'],
                                     u.bountyteam_poll_seconds or 3)
                            if t0 - last_scan.get(key, 0) >= iv:
                                try:
                                    scan_bountyteam(u, light=True)
                                except Exception as e:
                                    print(f'[fast-poll] bt {u.username}: {e}')
                                last_scan[key] = t0
                        # ---- 360 众测 ----
                        if u.zc_fast_poll and (u.zc_cookie or '').strip():
                            key = ('zc', u.id)
                            iv = max(PLATFORM_MIN_SECONDS['zc'],
                                     u.zc_interval_seconds or 3)
                            if t0 - last_scan.get(key, 0) >= iv:
                                try:
                                    from app.zc_monitor import scan_zc
                                    scan_zc(u, light=True)
                                except Exception as e:
                                    print(f'[fast-poll] zc {u.username}: {e}')
                                last_scan[key] = t0
                        # ---- 补天 + 漏洞盒子 (SRC) ----
                        if u.src_fast_poll:
                            key = ('src', u.id)
                            iv = max(PLATFORM_MIN_SECONDS['src'],
                                     u.src_poll_seconds or 5)
                            if t0 - last_scan.get(key, 0) >= iv:
                                try:
                                    from app.src_monitor import scan_src_platforms
                                    scan_src_platforms(u, light=True)
                                except Exception as e:
                                    print(f'[fast-poll] src {u.username}: {e}')
                                last_scan[key] = t0
            except Exception as e:
                err = True
                print(f'[fast-poll] error: {e}')

            elapsed_ms = (time.monotonic() - t0) * 1000
            _fast_state['avg_latency_ms'] = round(elapsed_ms)
            _fast_state['last_poll_at'] = datetime.now(timezone.utc).isoformat()
            _fast_state['poll_count'] += 1

            # 异常退避, 正常时按配置间隔(±20%抖动)
            if err:
                backoff = min(backoff * 2, 60.0)
                sleep_s = backoff
            else:
                backoff = 1.0
                base = _get_poll_seconds(app)
                sleep_s = base * random.uniform(0.8, 1.2)

            _fast_state['stop'].wait(sleep_s)
    finally:
        _fast_state['running'] = False


def start_fast_poll(app):
    """启动极速轮询线程 (幂等)。"""
    if _fast_state['thread'] and _fast_state['thread'].is_alive():
        return
    _fast_state['stop'].clear()
    t = threading.Thread(target=_fast_poll_loop, args=(app,), daemon=True,
                         name='bountyteam-fast-poll')
    _fast_state['thread'] = t
    t.start()
    print('[fast-poll] 极速轮询线程已启动')


def stop_fast_poll():
    """停止极速轮询线程。"""
    _fast_state['stop'].set()
    t = _fast_state['thread']
    if t and t.is_alive():
        t.join(timeout=5)
    _fast_state['thread'] = None
    print('[fast-poll] 极速轮询线程已停止')


def any_fast_poll_enabled() -> bool:
    """是否有用户开启了任一平台的极速模式 (用于调度决策)。"""
    try:
        return bool(
            User.query.filter_by(bountyteam_fast_poll=True).first()
            or User.query.filter_by(zc_fast_poll=True).first()
            or User.query.filter_by(src_fast_poll=True).first()
        )
    except Exception:
        return False
