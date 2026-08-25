"""SRC platform monitor — Butian & Vulbox."""
from datetime import datetime, timezone
import requests
from app import db
from app.models import SrcProgram


BUTIAN_TABS = {
    'corps': {'url': 'https://www.butian.net/Reward/corps', 'label': '企业SRC'},
    'com':   {'url': 'https://www.butian.net/Reward/com',   'label': '专属SRC'},
    'pub':   {'url': 'https://www.butian.net/Reward/pub',   'label': '公益SRC'},
}

VULBOX_URL = 'https://vapi.vulbox.com/web/project/enterprise/src'


def _fetch_butian_tab(url: str) -> list:
    """Fetch a single Butian tab. Returns list of company dicts."""
    results = []
    try:
        resp = requests.post(
            url,
            data={'ajax': '1', 'name': '', 'sort': '1'},
            headers={
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json',
                'Referer': 'https://www.butian.net/Reward/plan/2',
            },
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('status') == 1 and 'data' in data:
                results = data['data'].get('list', [])
    except Exception:
        pass
    return results


def _fetch_vulbox(light: bool = False) -> list:
    """Fetch all Vulbox SRC programs. Returns list of program dicts."""
    results = []
    page = 1
    while True:
        try:
            resp = requests.get(
                VULBOX_URL,
                params={
                    'activity': '0',
                    'order_by': 'normal',
                    'page': page,
                    'page_size': 50,
                },
                headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Accept': 'application/json',
                    'Referer': 'https://src.vulbox.com/',
                },
                timeout=30,
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            if data.get('code') != 200:
                break
            page_data = data.get('data', {})
            results.extend(page_data.get('data', []))
            # 秒级模式只拉第一页
            if light:
                break
            if page >= page_data.get('last_page', 1):
                break
            page += 1
        except Exception:
            break
    return results


def scan_src_platforms(user, light: bool = False) -> tuple:
    """Scan all SRC platforms for a given user. Returns (total, new_count).

    light=True: 秒级轮询模式 — 补天只拉最新 tab 首页、漏洞盒子只拉第 1 页,
    降低单轮请求量, 适配秒级频率。
    """
    now = datetime.now(timezone.utc)
    total, new_count = 0, 0

    # --- Butian ---
    tab_keys = list(BUTIAN_TABS.keys())
    if light:
        tab_keys = tab_keys[:1]  # 秒级只扫第一个 tab (企业SRC)
    for tab_key in tab_keys:
        tab_info = BUTIAN_TABS[tab_key]
        companies = _fetch_butian_tab(tab_info['url'])
        for c in companies:
            cid = str(c.get('company_id', ''))
            if not cid:
                continue
            existing = SrcProgram.query.filter_by(
                user_id=user.id, platform='butian', company_id=cid,
            ).first()
            if existing:
                existing.last_seen = now
                ct = c.get('change_time', '')
                if ct:
                    try:
                        existing.change_time = datetime.strptime(ct, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        pass
                existing.recommend = c.get('recommend') == '1'
                existing.service_status = str(c.get('service_status', ''))
            else:
                ct = c.get('change_time', '')
                ct_dt = None
                if ct:
                    try:
                        ct_dt = datetime.strptime(ct, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        pass
                db.session.add(SrcProgram(
                    user_id=user.id,
                    platform='butian',
                    tab=tab_key,
                    company_id=cid,
                    company_name=c.get('company_name', ''),
                    reward_min=int(c.get('min_reward', 0) or 0),
                    reward_max=int(c.get('max_reward', 0) or 0),
                    description=c.get('introduce', ''),
                    change_time=ct_dt,
                    recommend=c.get('recommend') == '1',
                    service_status=str(c.get('service_status', '')),
                    is_new=True,
                ))
                new_count += 1
            total += 1
        db.session.commit()

    # --- Vulbox ---
    programs = _fetch_vulbox(light=light)
    for p in programs:
        cid = str(p.get('id', ''))
        if not cid:
            continue
        existing = SrcProgram.query.filter_by(
            user_id=user.id, platform='vulbox', company_id=cid,
        ).first()
        if existing:
            existing.last_seen = now
        else:
            stime = p.get('task_stime', '')
            st_dt = None
            if stime:
                try:
                    st_dt = datetime.strptime(stime, '%Y-%m-%d %H:%M')
                except ValueError:
                    pass
            reward = p.get('reward_range', '0 ~ 0')
            parts = reward.replace(' ', '').split('~')
            rmin, rmax = 0, 0
            try:
                rmin = int(parts[0]) if parts[0] else 0
                rmax = int(parts[1]) if len(parts) > 1 and parts[1] else 0
            except (ValueError, IndexError):
                pass

            db.session.add(SrcProgram(
                user_id=user.id,
                platform='vulbox',
                tab='enterprise',
                company_id=cid,
                company_name=p.get('task_title', ''),
                reward_min=rmin,
                reward_max=rmax,
                description=p.get('task_desc', ''),
                change_time=st_dt,
                recommend=False,
                service_status='',
                is_new=True,
            ))
            new_count += 1
        total += 1
    db.session.commit()

    return total, new_count
