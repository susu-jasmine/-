from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from app import db
from app.models import User, Domain, Asset, ScanLog, SrcProgram, BountyProject
from app.auth import token_required
from app.scanner import scan_domain
from app.notifier import notify_new_assets
from app.src_monitor import scan_src_platforms
from app.scheduler import (
    add_domain_job, remove_domain_job,
    pause_domain_job, resume_domain_job,
)

api_bp = Blueprint('api', __name__)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
@api_bp.route('/settings', methods=['PUT'])
@token_required
def update_settings(current_user):
    data = request.get_json(silent=True) or {}
    fields = [
        'email', 'pushplus_token', 'smtp_host', 'smtp_port',
        'smtp_user', 'smtp_pass', 'smtp_from',
        'notify_email', 'notify_wechat', 'src_interval_hours',
    ]
    for f in fields:
        if f in data:
            setattr(current_user, f, data[f])
    # BountyTeam 配置
    if 'bountyteam_token' in data:
        current_user.bountyteam_token = (data['bountyteam_token'] or '').strip()
    if 'bountyteam_interval_minutes' in data:
        try:
            current_user.bountyteam_interval_minutes = max(1, int(data['bountyteam_interval_minutes']))
        except (TypeError, ValueError):
            pass
    if 'bountyteam_auto_apply' in data:
        current_user.bountyteam_auto_apply = bool(data['bountyteam_auto_apply'])
    if 'bountyteam_fast_poll' in data:
        current_user.bountyteam_fast_poll = bool(data['bountyteam_fast_poll'])
    if 'bountyteam_poll_seconds' in data:
        try:
            current_user.bountyteam_poll_seconds = max(0.2, min(60, float(data['bountyteam_poll_seconds'])))
        except (TypeError, ValueError):
            pass
    # 360 众测配置
    if 'zc_cookie' in data:
        current_user.zc_cookie = (data['zc_cookie'] or '').strip()
    if 'zc_interval_seconds' in data:
        try:
            current_user.zc_interval_seconds = max(0.5, min(60, float(data['zc_interval_seconds'])))
        except (TypeError, ValueError):
            pass
    if 'zc_auto_apply' in data:
        current_user.zc_auto_apply = bool(data['zc_auto_apply'])
    if 'zc_fast_poll' in data:
        current_user.zc_fast_poll = bool(data['zc_fast_poll'])
    # 补天/漏洞盒子 秒级配置
    if 'src_fast_poll' in data:
        current_user.src_fast_poll = bool(data['src_fast_poll'])
    if 'src_poll_seconds' in data:
        try:
            current_user.src_poll_seconds = max(2, min(60, float(data['src_poll_seconds'])))
        except (TypeError, ValueError):
            pass
    db.session.commit()
    # Reschedule SRC scan if interval changed
    if 'src_interval_hours' in data:
        from app.scheduler import reschedule_src_scan
        reschedule_src_scan()
    # 重新调度 bountyteam (token / 间隔 / 极速模式变化)
    _bt_keys = ('bountyteam_token', 'bountyteam_interval_minutes',
                'bountyteam_fast_poll', 'bountyteam_poll_seconds',
                'zc_cookie', 'zc_interval_seconds', 'zc_fast_poll',
                'src_fast_poll', 'src_poll_seconds')
    if any(k in data for k in _bt_keys):
        from app.scheduler import reschedule_bountyteam_scan
        reschedule_bountyteam_scan()
    return jsonify({'message': 'Settings updated'})


# ---------------------------------------------------------------------------
# Domains
# ---------------------------------------------------------------------------
@api_bp.route('/domains', methods=['GET'])
@token_required
def list_domains(current_user):
    sort_by = request.args.get('sort_by', 'created_at')
    sort_asc = request.args.get('sort_asc', '0') == '1'
    org_filter = request.args.get('organization', '').strip()
    col_map = {
        'domain': Domain.domain, 'status': Domain.status,
        'interval_hours': Domain.interval_hours, 'last_scan_at': Domain.last_scan_at,
        'created_at': Domain.created_at, 'organization': Domain.organization,
    }
    col = col_map.get(sort_by, Domain.created_at)
    order = col.asc() if sort_asc else col.desc()
    q = Domain.query.filter_by(user_id=current_user.id)
    if org_filter:
        q = q.filter_by(organization=org_filter)
    if sort_by == 'asset_count':
        domains = q.all()
        domains.sort(key=lambda d: Asset.query.filter_by(domain_id=d.id).count(), reverse=not sort_asc)
    else:
        domains = q.order_by(order).all()
    result = []
    for d in domains:
        asset_count = Asset.query.filter_by(domain_id=d.id).count()
        new_count = Asset.query.filter_by(domain_id=d.id, is_new=True).count()
        result.append({
            'id': d.id,
            'domain': d.domain,
            'organization': d.organization,
            'status': d.status,
            'interval_hours': d.interval_hours,
            'created_at': d.created_at.isoformat(),
            'last_scan_at': d.last_scan_at.isoformat() if d.last_scan_at else None,
            'asset_count': asset_count,
            'new_count': new_count,
        })
    return jsonify(result)


@api_bp.route('/domains', methods=['POST'])
@token_required
def create_domain(current_user):
    data = request.get_json(silent=True) or {}
    name = data.get('domain', '').strip().lower()

    if not name or '.' not in name:
        return jsonify({'error': 'Invalid domain'}), 400

    if Domain.query.filter_by(user_id=current_user.id, domain=name).first():
        return jsonify({'error': 'Domain already monitored'}), 409

    org = data.get('organization', '').strip()
    interval = max(1, int(data.get('interval_hours', 6)))

    d = Domain(
        user_id=current_user.id, domain=name,
        organization=org, interval_hours=interval,
    )
    db.session.add(d)
    db.session.commit()

    add_domain_job(d)

    new_count, all_subs = scan_domain(d)
    if new_count > 0:
        new_assets = (
            Asset.query.filter_by(domain_id=d.id, is_new=True)
            .order_by(Asset.first_seen.desc())
            .limit(new_count).all()
        )
        notify_new_assets(current_user, name, [a.subdomain for a in new_assets])

    return jsonify({
        'id': d.id, 'domain': d.domain, 'status': d.status,
        'asset_count': len(all_subs), 'new_count': new_count,
    }), 201


@api_bp.route('/domains/<int:domain_id>', methods=['PUT'])
@token_required
def update_domain(current_user, domain_id):
    d = Domain.query.filter_by(id=domain_id, user_id=current_user.id).first()
    if not d:
        return jsonify({'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    if 'interval_hours' in data:
        d.interval_hours = max(1, int(data['interval_hours']))
        add_domain_job(d)
    if 'organization' in data:
        d.organization = data['organization'].strip()
    db.session.commit()
    return jsonify({'message': 'Updated'})


@api_bp.route('/domains/<int:domain_id>', methods=['DELETE'])
@token_required
def delete_domain(current_user, domain_id):
    d = Domain.query.filter_by(id=domain_id, user_id=current_user.id).first()
    if not d:
        return jsonify({'error': 'Not found'}), 404
    remove_domain_job(domain_id)
    db.session.delete(d)
    db.session.commit()
    return jsonify({'message': 'Deleted'})


@api_bp.route('/domains/batch', methods=['POST'])
@token_required
def batch_create_domains(current_user):
    """Batch import domains under an organization."""
    data = request.get_json(silent=True) or {}
    org = data.get('organization', '').strip()
    domains_text = data.get('domains', '')
    interval = max(1, int(data.get('interval_hours', 6)))

    # Parse domains: newline, comma, or space separated
    names = set()
    for part in domains_text.replace('\n', ',').replace(' ', ',').split(','):
        d = part.strip().lower()
        if d and '.' in d:
            names.add(d)

    if not names:
        return jsonify({'error': 'No valid domains found'}), 400

    added, skipped = [], []
    for name in sorted(names):
        if len(name) > 256:
            continue
        if Domain.query.filter_by(user_id=current_user.id, domain=name).first():
            skipped.append(name)
            continue
        d = Domain(
            user_id=current_user.id,
            domain=name,
            organization=org,
            interval_hours=interval,
        )
        db.session.add(d)
        db.session.commit()
        add_domain_job(d)
        added.append(name)
        # Run first scan (non-blocking per domain)
        try:
            scan_domain(d)
        except Exception:
            pass

    if added:
        # Notify for all newly added
        total_new = Asset.query.filter(
            Asset.domain_id.in_(
                [d.id for d in Domain.query.filter_by(user_id=current_user.id).all()]
            ),
            Asset.is_new == True,
        ).count()
        if total_new > 0 and current_user.notify_wechat:
            from app.notifier import notify_new_assets
            # Just notify once, not per domain

    return jsonify({
        'message': f'Imported {len(added)} domains, skipped {len(skipped)}',
        'added': added,
        'skipped': skipped,
    }), 201


@api_bp.route('/domains/<int:domain_id>/pause', methods=['POST'])
@token_required
def pause_domain(current_user, domain_id):
    d = Domain.query.filter_by(id=domain_id, user_id=current_user.id).first()
    if not d:
        return jsonify({'error': 'Not found'}), 404
    d.status = 'paused'
    db.session.commit()
    pause_domain_job(domain_id)
    return jsonify({'message': 'Paused'})


@api_bp.route('/domains/<int:domain_id>/resume', methods=['POST'])
@token_required
def resume_domain(current_user, domain_id):
    d = Domain.query.filter_by(id=domain_id, user_id=current_user.id).first()
    if not d:
        return jsonify({'error': 'Not found'}), 404
    d.status = 'active'
    db.session.commit()
    resume_domain_job(domain_id)
    return jsonify({'message': 'Resumed'})


@api_bp.route('/domains/<int:domain_id>/scan', methods=['POST'])
@token_required
def trigger_scan(current_user, domain_id):
    d = Domain.query.filter_by(id=domain_id, user_id=current_user.id).first()
    if not d:
        return jsonify({'error': 'Not found'}), 404

    new_count, all_subs = scan_domain(d)
    if new_count > 0:
        new_assets = (
            Asset.query.filter_by(domain_id=domain_id, is_new=True)
            .order_by(Asset.first_seen.desc())
            .limit(new_count).all()
        )
        notify_new_assets(current_user, d.domain, [a.subdomain for a in new_assets])

    return jsonify({
        'message': 'Scan completed', 'assets_found': len(all_subs),
        'new_count': new_count,
    })


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------
@api_bp.route('/organizations', methods=['GET'])
@token_required
def list_organizations(current_user):
    rows = (
        Domain.query.filter_by(user_id=current_user.id)
        .filter(Domain.organization != '')
        .with_entities(Domain.organization)
        .distinct()
        .order_by(Domain.organization)
        .all()
    )
    orgs = [r[0] for r in rows if r[0]]
    # Count domains per org
    result = []
    for org in orgs:
        count = Domain.query.filter_by(user_id=current_user.id, organization=org).count()
        result.append({'name': org, 'domain_count': count})
    return jsonify(result)


def _user_domain_ids(user) -> list:
    return [d.id for d in Domain.query.filter_by(user_id=user.id).all()]


@api_bp.route('/domains/<int:domain_id>/assets', methods=['GET'])
@token_required
def list_assets(current_user, domain_id):
    d = Domain.query.filter_by(id=domain_id, user_id=current_user.id).first()
    if not d:
        return jsonify({'error': 'Not found'}), 404

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)
    only_new = request.args.get('new_only', '0') == '1'
    search = request.args.get('search', '').strip()

    q = Asset.query.filter_by(domain_id=domain_id)
    if only_new:
        q = q.filter_by(is_new=True)
    if search:
        q = q.filter(Asset.subdomain.contains(search))

    sort_by = request.args.get('sort_by', 'first_seen')
    sort_asc = request.args.get('sort_asc', '0') == '1'
    col_map = {
        'subdomain': Asset.subdomain, 'ip_addresses': Asset.ip_addresses,
        'source': Asset.source, 'first_seen': Asset.first_seen,
        'last_seen': Asset.last_seen,
    }
    col = col_map.get(sort_by, Asset.first_seen)
    order = col.asc() if sort_asc else col.desc()

    total = q.count()
    assets = q.order_by(order).offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        'assets': [_asset_dict(a) for a in assets],
        'total': total, 'page': page, 'per_page': per_page,
    })


@api_bp.route('/assets', methods=['GET'])
@token_required
def all_assets(current_user):
    ids = _user_domain_ids(current_user)
    if not ids:
        return jsonify({'assets': [], 'total': 0, 'page': 1, 'per_page': 50})

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)
    only_new = request.args.get('new_only', '0') == '1'
    search = request.args.get('search', '').strip()

    q = Asset.query.filter(Asset.domain_id.in_(ids))
    if only_new:
        q = q.filter_by(is_new=True)
    if search:
        q = q.filter(Asset.subdomain.contains(search))

    sort_by = request.args.get('sort_by', 'first_seen')
    sort_asc = request.args.get('sort_asc', '0') == '1'
    col_map = {
        'subdomain': Asset.subdomain, 'ip_addresses': Asset.ip_addresses,
        'source': Asset.source, 'first_seen': Asset.first_seen,
        'last_seen': Asset.last_seen,
    }
    col = col_map.get(sort_by, Asset.first_seen)
    order = col.asc() if sort_asc else col.desc()

    total = q.count()
    assets = q.order_by(order).offset((page - 1) * per_page).limit(per_page).all()

    domain_map = {
        d.id: d.domain
        for d in Domain.query.filter(Domain.id.in_(ids)).all()
    }

    return jsonify({
        'assets': [_asset_dict(a, domain_map.get(a.domain_id, '')) for a in assets],
        'total': total, 'page': page, 'per_page': per_page,
    })


@api_bp.route('/assets/mark-all-seen', methods=['POST'])
@token_required
def mark_all_assets_seen(current_user):
    data = request.get_json(silent=True) or {}
    domain_id = data.get('domain_id')
    ids = _user_domain_ids(current_user)
    if not ids:
        return jsonify({'message': 'No assets'})

    q = Asset.query.filter(Asset.domain_id.in_(ids), Asset.is_new == True)  # noqa: E712
    if domain_id:
        q = q.filter(Asset.domain_id == domain_id)

    count = q.update({Asset.is_new: False})
    db.session.commit()
    return jsonify({'message': f'Marked {count} as seen'})


@api_bp.route('/assets/<int:asset_id>/mark-seen', methods=['POST'])
@token_required
def mark_asset_seen(current_user, asset_id):
    ids = _user_domain_ids(current_user)
    if not ids:
        return jsonify({'error': 'Not found'}), 404

    asset = Asset.query.filter(
        Asset.id == asset_id, Asset.domain_id.in_(ids),
    ).first()
    if not asset:
        return jsonify({'error': 'Not found'}), 404

    asset.is_new = False
    db.session.commit()
    return jsonify({'message': 'Marked as seen'})


@api_bp.route('/assets/export', methods=['GET'])
@token_required
def export_assets(current_user):
    fmt = request.args.get('format', 'csv')
    only_new = request.args.get('new_only', '0') == '1'
    ids = _user_domain_ids(current_user)

    if not ids:
        return '', 200, {'Content-Type': 'text/csv'}

    domain_map = {
        d.id: d.domain
        for d in Domain.query.filter(Domain.id.in_(ids)).all()
    }

    q = Asset.query.filter(Asset.domain_id.in_(ids))
    if only_new:
        q = q.filter_by(is_new=True)
    assets = q.order_by(Asset.first_seen.desc()).all()

    if fmt == 'json':
        return jsonify([
            {
                'subdomain': a.subdomain,
                'domain': domain_map.get(a.domain_id, ''),
                'ip_addresses': a.ip_addresses,
                'source': a.source,
                'first_seen': a.first_seen.isoformat(),
                'is_new': a.is_new,
            } for a in assets
        ])

    lines = ['subdomain,domain,ip_addresses,source,first_seen,is_new']
    for a in assets:
        lines.append(
            f'"{a.subdomain}","{domain_map.get(a.domain_id, "")}",'
            f'"{a.ip_addresses}","{a.source}","{a.first_seen.isoformat()}",'
            f'"{a.is_new}"'
        )

    return '\n'.join(lines), 200, {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': 'attachment; filename=assets.csv',
    }


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
@api_bp.route('/stats', methods=['GET'])
@token_required
def get_stats(current_user):
    ids = _user_domain_ids(current_user)
    if not ids:
        return jsonify({
            'total_domains': 0, 'active_domains': 0,
            'total_assets': 0, 'new_assets': 0, 'today_new': 0,
        })

    domains = Domain.query.filter(Domain.id.in_(ids)).all()
    total_domains = len(domains)
    active_domains = sum(1 for d in domains if d.status == 'active')
    total_assets = Asset.query.filter(Asset.domain_id.in_(ids)).count()
    new_assets = Asset.query.filter(
        Asset.domain_id.in_(ids), Asset.is_new == True,  # noqa: E712
    ).count()

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_new = Asset.query.filter(
        Asset.domain_id.in_(ids), Asset.first_seen >= today,
    ).count()

    return jsonify({
        'total_domains': total_domains,
        'active_domains': active_domains,
        'total_assets': total_assets,
        'new_assets': new_assets,
        'today_new': today_new,
    })


# ---------------------------------------------------------------------------
# Scan logs
# ---------------------------------------------------------------------------
@api_bp.route('/scan-logs', methods=['GET'])
@token_required
def scan_logs(current_user):
    domain_id = request.args.get('domain_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    if domain_id:
        d = Domain.query.filter_by(id=domain_id, user_id=current_user.id).first()
        if not d:
            return jsonify({'error': 'Not found'}), 404
        q = ScanLog.query.filter_by(domain_id=domain_id)
    else:
        ids = _user_domain_ids(current_user)
        if not ids:
            return jsonify({'logs': [], 'total': 0, 'page': 1, 'per_page': per_page})
        q = ScanLog.query.filter(ScanLog.domain_id.in_(ids))

    sort_by = request.args.get('sort_by', 'started_at')
    sort_asc = request.args.get('sort_asc', '0') == '1'
    col_map = {
        'started_at': ScanLog.started_at, 'finished_at': ScanLog.finished_at,
        'assets_found': ScanLog.assets_found, 'new_assets_found': ScanLog.new_assets_found,
        'status': ScanLog.status,
    }
    col = col_map.get(sort_by, ScanLog.started_at)
    order = col.asc() if sort_asc else col.desc()

    total = q.count()
    logs = q.order_by(order).offset((page - 1) * per_page).limit(per_page).all()

    domain_map = {
        d.id: d.domain
        for d in Domain.query.filter_by(user_id=current_user.id).all()
    }

    return jsonify({
        'logs': [{
            'id': l.id,
            'domain': domain_map.get(l.domain_id, ''),
            'started_at': l.started_at.isoformat(),
            'finished_at': l.finished_at.isoformat() if l.finished_at else None,
            'assets_found': l.assets_found,
            'new_assets_found': l.new_assets_found,
            'status': l.status,
        } for l in logs],
        'total': total, 'page': page, 'per_page': per_page,
    })


# ---------------------------------------------------------------------------
# SRC Platform Monitor
# ---------------------------------------------------------------------------
@api_bp.route('/src-programs', methods=['GET'])
@token_required
def list_src_programs(current_user):
    platform = request.args.get('platform', '')
    only_new = request.args.get('new_only', '0') == '1'
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)
    search = request.args.get('search', '').strip()

    q = SrcProgram.query.filter_by(user_id=current_user.id)
    if platform:
        q = q.filter_by(platform=platform)
    if only_new:
        q = q.filter_by(is_new=True)
    if search:
        q = q.filter(SrcProgram.company_name.contains(search))

    sort_by = request.args.get('sort_by', 'first_seen')
    sort_asc = request.args.get('sort_asc', '0') == '1'
    col_map = {
        'platform': SrcProgram.platform, 'company_name': SrcProgram.company_name,
        'reward_max': SrcProgram.reward_max, 'change_time': SrcProgram.change_time,
        'first_seen': SrcProgram.first_seen,
    }
    col = col_map.get(sort_by, SrcProgram.first_seen)
    order = col.asc() if sort_asc else col.desc()

    total = q.count()
    programs = q.order_by(order).offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        'programs': [{
            'id': p.id,
            'platform': p.platform,
            'tab': p.tab,
            'company_name': p.company_name,
            'reward_min': p.reward_min,
            'reward_max': p.reward_max,
            'description': p.description,
            'change_time': p.change_time.isoformat() if p.change_time else None,
            'recommend': p.recommend,
            'is_new': p.is_new,
            'first_seen': p.first_seen.isoformat(),
        } for p in programs],
        'total': total, 'page': page, 'per_page': per_page,
    })


@api_bp.route('/src-programs/mark-all-seen', methods=['POST'])
@token_required
def mark_all_src_seen(current_user):
    q = SrcProgram.query.filter_by(user_id=current_user.id, is_new=True)
    count = q.update({SrcProgram.is_new: False})
    db.session.commit()
    return jsonify({'message': f'Marked {count} as seen'})


@api_bp.route('/src-programs/<int:program_id>/mark-seen', methods=['POST'])
@token_required
def mark_src_seen(current_user, program_id):
    p = SrcProgram.query.filter_by(id=program_id, user_id=current_user.id).first()
    if not p:
        return jsonify({'error': 'Not found'}), 404
    p.is_new = False
    db.session.commit()
    return jsonify({'message': 'Marked as seen'})


@api_bp.route('/src-programs/scan', methods=['POST'])
@token_required
def trigger_src_scan(current_user):
    total, new_count = scan_src_platforms(current_user)
    if new_count > 0:
        from app.notifier import notify_new_assets
        new_programs = (
            SrcProgram.query.filter_by(user_id=current_user.id, is_new=True)
            .order_by(SrcProgram.first_seen.desc())
            .limit(new_count)
            .all()
        )
        _notify_new_src(current_user, [p.company_name for p in new_programs], new_count)
    return jsonify({'message': 'SRC scan completed', 'total': total, 'new_count': new_count})


@api_bp.route('/src-stats', methods=['GET'])
@token_required
def src_stats(current_user):
    total = SrcProgram.query.filter_by(user_id=current_user.id).count()
    new = SrcProgram.query.filter_by(user_id=current_user.id, is_new=True).count()
    butian = SrcProgram.query.filter_by(user_id=current_user.id, platform='butian').count()
    vulbox = SrcProgram.query.filter_by(user_id=current_user.id, platform='vulbox').count()
    return jsonify({
        'total': total, 'new': new,
        'butian': butian, 'vulbox': vulbox,
    })


@api_bp.route('/src-programs/export', methods=['GET'])
@token_required
def export_src(current_user):
    fmt = request.args.get('format', 'csv')
    only_new = request.args.get('new_only', '0') == '1'

    q = SrcProgram.query.filter_by(user_id=current_user.id)
    if only_new:
        q = q.filter_by(is_new=True)
    programs = q.order_by(SrcProgram.first_seen.desc()).all()

    if fmt == 'json':
        return jsonify([{
            'platform': p.platform,
            'tab': p.tab,
            'company_name': p.company_name,
            'reward_range': f'{p.reward_min}~{p.reward_max}',
            'description': p.description,
            'change_time': p.change_time.isoformat() if p.change_time else '',
            'first_seen': p.first_seen.isoformat(),
            'is_new': p.is_new,
        } for p in programs])

    lines = ['platform,tab,company_name,reward_min,reward_max,description,change_time,first_seen,is_new']
    for p in programs:
        lines.append(
            f'"{p.platform}","{p.tab}","{p.company_name}",'
            f'{p.reward_min},{p.reward_max},"{p.description}",'
            f'"{p.change_time.isoformat() if p.change_time else ""}",'
            f'"{p.first_seen.isoformat()}","{p.is_new}"'
        )

    return '\n'.join(lines), 200, {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': 'attachment; filename=src_programs.csv',
    }


def _notify_new_src(user, company_names: list, count: int):
    if user.notify_wechat and user.pushplus_token:
        from app.notifier import send_pushplus
        preview = '<br>'.join(company_names[:15])
        more = f'<br>... 等共 {count} 个' if count > 15 else ''
        send_pushplus(
            user.pushplus_token,
            f'[AssetMonitor] SRC平台 +{count} 新企业',
            f'<h3>🔍 SRC新企业通知</h3>'
            f'<p>新上线: <b>{count}</b> 个企业SRC</p>'
            f'<hr><pre>{preview}{more}</pre><hr>'
            f'<small>Asset Monitor System</small>',
        )
    if user.notify_email and user.email and user.smtp_host:
        from app.notifier import send_email
        preview = '<br>'.join(company_names[:15])
        more = f'<br>... 等共 {count} 个' if count > 15 else ''
        send_email(
            {
                'host': user.smtp_host, 'port': user.smtp_port,
                'user': user.smtp_user, 'pass': user.smtp_pass,
                'from': user.smtp_from,
            },
            user.email,
            f'[AssetMonitor] SRC平台 +{count} 新企业',
            f'<h3>🔍 SRC新企业通知</h3>'
            f'<p>新上线: <b>{count}</b> 个企业SRC</p>'
            f'<hr><pre>{preview}{more}</pre><hr>'
            f'<small>Asset Monitor System</small>',
        )


# ---------------------------------------------------------------------------
# BountyTeam (雷神众测) 项目监控
# ---------------------------------------------------------------------------
@api_bp.route('/bounty/projects', methods=['GET'])
@token_required
def list_bounty_projects(current_user):
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)
    only_new = request.args.get('new_only', '0') == '1'
    only_open = request.args.get('open_only', '1') == '1'
    search = request.args.get('search', '').strip()

    q = BountyProject.query.filter_by(user_id=current_user.id)
    if only_open:
        q = q.filter_by(is_open=True)
    if only_new:
        q = q.filter_by(is_new=True)
    if search:
        q = q.filter(BountyProject.name.contains(search))

    sort_by = request.args.get('sort_by', 'first_seen')
    sort_asc = request.args.get('sort_asc', '0') == '1'
    col_map = {
        'name': BountyProject.name, 'reward_max': BountyProject.reward_max,
        'surplus': BountyProject.surplus, 'startime': BountyProject.startime,
        'first_seen': BountyProject.first_seen,
    }
    col = col_map.get(sort_by, BountyProject.first_seen)
    order = col.asc() if sort_asc else col.desc()

    total = q.count()
    rows = q.order_by(order).offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        'projects': [{
            'id': p.id,
            'project_id': p.project_id,
            'name': p.name,
            'project_type': p.project_type,
            'states': p.states,
            'startime': p.startime.isoformat() if p.startime else None,
            'surplus': p.surplus,
            'remainder_num': p.remainder_num,
            'reward_min': p.reward_min,
            'reward_max': p.reward_max,
            'detail_url': p.detail_url,
            'is_new': p.is_new,
            'is_open': p.is_open,
            'apply_status': p.apply_status,
            'apply_err': p.apply_err,
            'apply_time': p.apply_time.isoformat() if p.apply_time else None,
            'first_seen': p.first_seen.isoformat(),
            'last_seen': p.last_seen.isoformat(),
        } for p in rows],
        'total': total, 'page': page, 'per_page': per_page,
    })


@api_bp.route('/bounty/scan', methods=['POST'])
@token_required
def trigger_bounty_scan(current_user):
    if not (current_user.bountyteam_token or '').strip():
        return jsonify({'error': '请先在设置中填写 BountyTeam Token'}), 400
    from app.bountyteam_monitor import scan_bountyteam
    total, new_count = scan_bountyteam(current_user)
    return jsonify({
        'message': 'BountyTeam scan completed',
        'total': total, 'new_count': new_count,
    })


@api_bp.route('/bounty/projects/mark-all-seen', methods=['POST'])
@token_required
def mark_all_bounty_seen(current_user):
    q = BountyProject.query.filter_by(user_id=current_user.id, is_new=True)
    count = q.update({BountyProject.is_new: False})
    db.session.commit()
    return jsonify({'message': f'Marked {count} as seen'})


@api_bp.route('/bounty/projects/<int:project_id>/apply', methods=['POST'])
@token_required
def manual_apply_bounty(current_user, project_id):
    """手动报名指定项目 (自动报名失败时重试)。"""
    p = BountyProject.query.filter_by(
        user_id=current_user.id, project_id=project_id,
    ).first()
    if not p:
        return jsonify({'error': 'Not found'}), 404
    token = (current_user.bountyteam_token or '').strip()
    if not token:
        return jsonify({'error': '请先在设置中填写 BountyTeam Token'}), 400
    from app.bountyteam_monitor import apply_project
    from datetime import datetime, timezone
    ok, msg, new_tok, st = apply_project(token, p.project_id)
    if new_tok and new_tok != token:
        current_user.bountyteam_token = new_tok
    p.apply_status = 'applied' if ok else 'failed'
    p.apply_time = datetime.now(timezone.utc)
    p.apply_err = '' if ok else msg[:256]
    db.session.commit()
    return jsonify({
        'ok': ok, 'message': msg, 'status': p.apply_status,
    })


@api_bp.route('/bounty/stats', methods=['GET'])
@token_required
def bounty_stats(current_user):
    total = BountyProject.query.filter_by(user_id=current_user.id).count()
    open_count = BountyProject.query.filter_by(
        user_id=current_user.id, is_open=True,
    ).count()
    new = BountyProject.query.filter_by(
        user_id=current_user.id, is_new=True, is_open=True,
    ).count()
    # token 健康状态 + 极速轮询状态
    from app.bountyteam_monitor import get_health, fast_poll_status
    health = get_health(current_user.id)
    fps = fast_poll_status()
    has_token = bool((current_user.bountyteam_token or '').strip())
    return jsonify({
        'total': total, 'open': open_count, 'new': new,
        'token_status': health.get('token_status', 'unknown' if has_token else 'expired'),
        'token_configured': has_token,
        'auto_apply': bool(current_user.bountyteam_auto_apply),
        'fast_poll': bool(current_user.bountyteam_fast_poll),
        'fast_poll_running': fps['running'],
        'poll_seconds': current_user.bountyteam_poll_seconds or 3,
        'poll_count': fps['poll_count'],
        'last_poll_at': fps['last_poll_at'],
        'last_latency_ms': fps['avg_latency_ms'],
        'last_ok_at': health.get('last_ok_at'),
        'last_err': health.get('last_err'),
    })


# ---------------------------------------------------------------------------
# 360 众测 (zhongce.360.net) 项目监控 API
# ---------------------------------------------------------------------------
@api_bp.route('/zc/projects', methods=['GET'])
@token_required
def list_zc_projects(current_user):
    from app.models import ZcProject
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)
    only_new = request.args.get('new_only', '0') == '1'
    only_open = request.args.get('open_only', '1') == '1'
    search = request.args.get('search', '').strip()

    q = ZcProject.query.filter_by(user_id=current_user.id)
    if only_open:
        q = q.filter_by(is_open=True)
    if only_new:
        q = q.filter_by(is_new=True)
    if search:
        q = q.filter(ZcProject.name.contains(search))

    sort_by = request.args.get('sort_by', 'first_seen')
    sort_asc = request.args.get('sort_asc', '0') == '1'
    col_map = {
        'name': ZcProject.name, 'reward_max': ZcProject.reward_max,
        'surplus': ZcProject.surplus, 'startime': ZcProject.startime,
        'first_seen': ZcProject.first_seen,
    }
    col = col_map.get(sort_by, ZcProject.first_seen)
    order = col.asc() if sort_asc else col.desc()

    total = q.count()
    rows = q.order_by(order).offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        'projects': [{
            'id': p.id,
            'project_id': p.project_id,
            'name': p.name,
            'project_type': p.project_type,
            'states': p.states,
            'startime': p.startime.isoformat() if p.startime else None,
            'surplus': p.surplus,
            'reward_min': p.reward_min,
            'reward_max': p.reward_max,
            'detail_url': p.detail_url,
            'is_new': p.is_new,
            'is_open': p.is_open,
            'apply_status': p.apply_status,
            'apply_err': p.apply_err,
            'apply_time': p.apply_time.isoformat() if p.apply_time else None,
            'first_seen': p.first_seen.isoformat(),
        } for p in rows],
        'total': total, 'page': page, 'per_page': per_page,
    })


@api_bp.route('/zc/scan', methods=['POST'])
@token_required
def trigger_zc_scan(current_user):
    if not (current_user.zc_cookie or '').strip():
        return jsonify({'error': '请先在设置中填写 360众测 Cookie'}), 400
    from app.zc_monitor import scan_zc
    total, new_count = scan_zc(current_user)
    return jsonify({
        'message': '360众测 scan completed',
        'total': total, 'new_count': new_count,
    })


@api_bp.route('/zc/projects/mark-all-seen', methods=['POST'])
@token_required
def mark_all_zc_seen(current_user):
    from app.models import ZcProject
    q = ZcProject.query.filter_by(user_id=current_user.id, is_new=True)
    count = q.update({ZcProject.is_new: False})
    db.session.commit()
    return jsonify({'message': f'Marked {count} as seen'})


@api_bp.route('/zc/projects/<int:project_id>/apply', methods=['POST'])
@token_required
def manual_apply_zc(current_user, project_id):
    """手动报名 360众测 项目 (自动报名失败时重试)。"""
    from app.models import ZcProject
    p = ZcProject.query.filter_by(
        user_id=current_user.id, project_id=project_id,
    ).first()
    if not p:
        return jsonify({'error': 'Not found'}), 404
    cookie = (current_user.zc_cookie or '').strip()
    if not cookie:
        return jsonify({'error': '请先在设置中填写 360众测 Cookie'}), 400
    from app.zc_monitor import apply_project
    from datetime import datetime, timezone
    ok, msg, st = apply_project(cookie, p.project_id)
    p.apply_status = 'applied' if ok else 'failed'
    p.apply_time = datetime.now(timezone.utc)
    p.apply_err = '' if ok else msg[:256]
    db.session.commit()
    return jsonify({
        'ok': ok, 'message': msg, 'status': p.apply_status,
    })


@api_bp.route('/zc/stats', methods=['GET'])
@token_required
def zc_stats(current_user):
    from app.models import ZcProject
    total = ZcProject.query.filter_by(user_id=current_user.id).count()
    open_count = ZcProject.query.filter_by(
        user_id=current_user.id, is_open=True,
    ).count()
    new = ZcProject.query.filter_by(
        user_id=current_user.id, is_new=True, is_open=True,
    ).count()
    from app.zc_monitor import get_health
    from app.bountyteam_monitor import fast_poll_status
    health = get_health(current_user.id)
    fps = fast_poll_status()
    has_cookie = bool((current_user.zc_cookie or '').strip())
    return jsonify({
        'total': total, 'open': open_count, 'new': new,
        'cookie_status': health.get('token_status', 'unknown' if has_cookie else 'expired'),
        'cookie_configured': has_cookie,
        'auto_apply': bool(current_user.zc_auto_apply),
        'fast_poll': bool(current_user.zc_fast_poll),
        'fast_poll_running': fps['running'],
        'poll_seconds': current_user.zc_interval_seconds or 3,
        'last_ok_at': health.get('last_ok_at'),
        'last_err': health.get('last_err'),
    })


def _bounty_rows(user, limit):
    return (
        BountyProject.query
        .filter_by(user_id=user.id, is_new=True, is_open=True)
        .order_by(BountyProject.first_seen.desc())
        .limit(limit)
        .all()
    )


def notify_bountyteam_new(user, names: list, details: list, kind: str = 'new'):
    """有新的可报名项目 (未报名 + 有余量)。立即推送。

    details 元素: (name, remainder, reward_min, reward_max, apply_status, apply_err)
    开启自动报名后 apply_status 反映报名结果, 推送内容直接标注。
    """
    count = len(details)
    if count == 0:
        return
    auto = bool(getattr(user, 'bountyteam_auto_apply', False))
    lines = []
    for row in details[:20]:
        name, rem, rmin, rmax = row[0], row[1], row[2], row[3]
        astat = row[4] if len(row) > 4 else ''
        aerr = row[5] if len(row) > 5 else ''
        reward = f'{rmin:g}~{rmax:g}元' if (rmax or rmin) else '-'
        rem_str = rem or '不限'
        tag = ''
        if astat == 'applied':
            tag = '  ✅已自动报名'
        elif astat == 'failed':
            tag = f'  ❌报名失败({aerr})'
        lines.append(f'• {name}  [余{rem_str}]  {reward}{tag}')
    preview = '<br>'.join(lines)
    more = f'<br>... 等共 {count} 个' if count > 20 else ''
    if auto:
        title = f'[抢名额] 雷神众测 +{count} 新项目已自动报名'
    else:
        title = f'[抢名额] 雷神众测 +{count} 新可报名项目'
    body = (
        f'<h3>⚡ 雷神众测 · 新的可报名项目</h3>'
        f'<p>检测到 <b>{count}</b> 个未报名且仍有名额的项目:</p>'
        f'<hr><pre style="line-height:1.6;">{preview}{more}</pre>'
        f'<hr><a href="https://www.bountyteam.com/hacker-service/bug-bounty-list">'
        f'前往项目大厅 →</a><br><small>Asset Monitor System</small>'
    )
    _dispatch_bounty_notify(user, title, body)


def notify_bountyteam_apply_result(user, ok_list: list, fail_list: list):
    """自动报名结果反馈 (成功/失败 各推一条, 失败带原因)。

    ok_list/fail_list: [(项目名, 平台提示), ...]
    """
    if not ok_list and not fail_list:
        return
    lines = []
    for name, msg in ok_list[:20]:
        lines.append(f'✅ {name}')
    for name, msg in fail_list[:20]:
        lines.append(f'❌ {name} ({msg})')
    preview = '<br>'.join(lines)
    more = f'<br>... 等共 {len(ok_list)+len(fail_list)} 个' if len(ok_list)+len(fail_list) > 20 else ''
    title = f'[自动报名] 成功{len(ok_list)} / 失败{len(fail_list)}'
    body = (
        f'<h3>⚡ 雷神众测 · 自动报名结果</h3>'
        f'<p>成功 <b style="color:green;">{len(ok_list)}</b> 个, '
        f'失败 <b style="color:red;">{len(fail_list)}</b> 个:</p>'
        f'<hr><pre style="line-height:1.6;">{preview}{more}</pre>'
        f'<hr><a href="https://www.bountyteam.com/hacker-service/bug-bounty-list">'
        f'前往项目大厅 →</a><br><small>Asset Monitor System</small>'
    )
    _dispatch_bounty_notify(user, title, body)


def notify_bountyteam_closed(user, names: list):
    """此前可报名的项目已结束/报满。"""
    count = len(names)
    preview = '<br>'.join('• ' + n for n in names[:15])
    more = f'<br>... 等共 {count} 个' if count > 15 else ''
    title = f'[名额没了] 雷神众测 {count} 个项目已关闭'
    body = (
        f'<h3>⛔ 雷神众测 · 项目关闭</h3>'
        f'<p>以下项目已报满或结束:</p>'
        f'<hr><pre>{preview}{more}</pre><hr>'
        f'<small>Asset Monitor System</small>'
    )
    _dispatch_bounty_notify(user, title, body)


def notify_bountyteam_reopen(user, names: list):
    """之前关闭的项目又重新有了名额。"""
    count = len(names)
    preview = '<br>'.join('• ' + n for n in names[:15])
    more = f'<br>... 等共 {count} 个' if count > 15 else ''
    title = f'[名额恢复] 雷神众测 {count} 个项目重新可报名'
    body = (
        f'<h3>🔄 雷神众测 · 名额恢复</h3>'
        f'<p>以下项目重新开放报名:</p>'
        f'<hr><pre>{preview}{more}</pre><hr>'
        f'<small>Asset Monitor System</small>'
    )
    _dispatch_bounty_notify(user, title, body)


def _dispatch_bounty_notify(user, title: str, body: str):
    """bountyteam 是抢名额场景, 只要配置了任一渠道就立即推。"""
    if user.notify_wechat and user.pushplus_token:
        from app.notifier import send_pushplus
        send_pushplus(user.pushplus_token, title, body)
    if user.notify_email and user.email and user.smtp_host:
        from app.notifier import send_email
        send_email(
            {
                'host': user.smtp_host, 'port': user.smtp_port,
                'user': user.smtp_user, 'pass': user.smtp_pass,
                'from': user.smtp_from,
            },
            user.email, title, body,
        )


def notify_bountyteam_token_expired(user):
    """token 已彻底失效(401), 需人工重新登录换 token。"""
    title = '[雷神众测] Token 已过期, 监控已暂停'
    body = (
        f'<h3>⚠️ 雷神众测 Token 失效</h3>'
        f'<p>监控程序检测到 BountyTeam 接口返回 <b>401 权限鉴定失败</b>, '
        f'当前 token 已过期, 抢名额监控已暂停。</p>'
        f'<hr>'
        f'<p><b>恢复步骤:</b></p>'
        f'<ol>'
        f'<li>登录 https://www.bountyteam.com</li>'
        f'<li>浏览器控制台执行 <code>localStorage.getItem("jwtToken")</code></li>'
        f'<li>复制返回的 UUID, 粘贴到本系统「设置 → 雷神众测监控」并保存</li>'
        f'</ol>'
        f'<hr><small>提示: 因登录含验证码, 无法自动续期, 请及时更换。</small>'
        f'<br><small>Asset Monitor System</small>'
    )
    _dispatch_bounty_notify(user, title, body)


# ---------------------------------------------------------------------------
# 360 众测 (zhongce.360.net) 通知
# ---------------------------------------------------------------------------
def _dispatch_zc_notify(user, title: str, body: str):
    if user.notify_wechat and user.pushplus_token:
        from app.notifier import send_pushplus
        send_pushplus(user.pushplus_token, title, body)
    if user.notify_email and user.email and user.smtp_host:
        from app.notifier import send_email
        send_email(
            {
                'host': user.smtp_host, 'port': user.smtp_port,
                'user': user.smtp_user, 'pass': user.smtp_pass,
                'from': user.smtp_from,
            },
            user.email, title, body,
        )


def notify_zc_new(user, names: list, details: list):
    """360 众测有新项目。details: (name, rmin, rmax, apply_status, apply_err)"""
    count = len(details)
    if count == 0:
        return
    lines = []
    for name, rmin, rmax, astat, aerr in details[:20]:
        reward = f'{rmin:g}~{rmax:g}元' if (rmax or rmin) else '-'
        tag = '  ✅已自动报名' if astat == 'applied' else (
            f'  ❌报名失败({aerr})' if astat == 'failed' else '')
        lines.append(f'• {name}  [{reward}]{tag}')
    preview = '<br>'.join(lines)
    more = f'<br>... 等共 {count} 个' if count > 20 else ''
    title = f'[360众测] 新增 {count} 个项目'
    body = (
        f'<h3>🔎 360众测 · 新项目</h3>'
        f'<p>检测到 <b>{count}</b> 个新项目:</p>'
        f'<hr><pre style="line-height:1.6;">{preview}{more}</pre>'
        f'<hr><a href="https://zhongce.360.net/hacker/project/">前往项目大厅 →</a>'
        f'<br><small>Asset Monitor System</small>'
    )
    _dispatch_zc_notify(user, title, body)


def notify_zc_apply_result(user, ok_list: list, fail_list: list):
    if not ok_list and not fail_list:
        return
    lines = [f'✅ {n}' for n, _ in ok_list[:20]]
    lines += [f'❌ {n} ({m})' for n, m in fail_list[:20]]
    preview = '<br>'.join(lines)
    more = f'<br>... 等共 {len(ok_list)+len(fail_list)} 个' if len(ok_list)+len(fail_list) > 20 else ''
    title = f'[360众测] 自动报名 成功{len(ok_list)}/失败{len(fail_list)}'
    body = (
        f'<h3>⚡ 360众测 · 自动报名结果</h3>'
        f'<p>成功 <b style="color:green;">{len(ok_list)}</b> 个, '
        f'失败 <b style="color:red;">{len(fail_list)}</b> 个:</p>'
        f'<hr><pre style="line-height:1.6;">{preview}{more}</pre>'
        f'<hr><a href="https://zhongce.360.net/hacker/project/">前往项目大厅 →</a>'
        f'<br><small>Asset Monitor System</small>'
    )
    _dispatch_zc_notify(user, title, body)


def notify_zc_closed(user, names: list):
    count = len(names)
    preview = '<br>'.join('• ' + n for n in names[:15])
    more = f'<br>... 等共 {count} 个' if count > 15 else ''
    _dispatch_zc_notify(
        user,
        f'[360众测] {count} 个项目已关闭',
        f'<h3>⛔ 360众测 · 项目关闭</h3>'
        f'<p>以下项目已结束/满员:</p><hr><pre>{preview}{more}</pre><hr>'
        f'<small>Asset Monitor System</small>',
    )


def notify_zc_reopen(user, names: list):
    count = len(names)
    preview = '<br>'.join('• ' + n for n in names[:15])
    more = f'<br>... 等共 {count} 个' if count > 15 else ''
    _dispatch_zc_notify(
        user,
        f'[360众测] {count} 个项目重新开放',
        f'<h3>🔄 360众测 · 名额恢复</h3>'
        f'<p>以下项目重新开放报名:</p><hr><pre>{preview}{more}</pre><hr>'
        f'<small>Asset Monitor System</small>',
    )


def notify_zc_token_expired(user):
    title = '[360众测] Cookie 已失效, 监控已暂停'
    body = (
        f'<h3>⚠️ 360众测 Cookie 失效</h3>'
        f'<p>监控程序检测到 360众测 接口返回 <b>401/未登录</b>, '
        f'当前 Cookie 已过期, 项目监控与自动报名已暂停。</p>'
        f'<hr><p><b>常见失效原因:</b></p><ul>'
        f'<li>你在浏览器<b>重新登录</b>过 360 账号 —— 新登录会踢掉旧会话 (单会话机制)</li>'
        f'<li>会话达到平台绝对过期时间 (持续请求无法无限续期)</li>'
        f'<li>更换了登录环境/IP 触发安全策略</li>'
        f'</ul>'
        f'<p><b>恢复步骤:</b></p><ol>'
        f'<li>浏览器登录 https://zhongce.360.net (登录后<b>不要再在其他地方重复登录</b>)</li>'
        f'<li>F12 → Network → 任意请求 → 复制完整 Cookie 请求头</li>'
        f'<li>粘贴到本系统「设置 → 360众测」并保存 (系统会自动接收后续续期)</li>'
        f'</ol>'
        f'<hr><small>Asset Monitor System</small>'
    )
    _dispatch_zc_notify(user, title, body)


# ---------------------------------------------------------------------------
# Online Update (git)
# ---------------------------------------------------------------------------
@api_bp.route('/update/check', methods=['POST'])
@token_required
def update_check(current_user):
    from app.updater import check_for_updates
    return jsonify(check_for_updates())


@api_bp.route('/update/apply', methods=['POST'])
@token_required
def update_apply(current_user):
    from app.updater import apply_update
    ok, msg = apply_update()
    return jsonify({'ok': ok, 'message': msg}), (200 if ok else 500)


@api_bp.route('/update/remote', methods=['GET'])
@token_required
def update_remote_get(current_user):
    from app.updater import _run
    rc, url, _ = _run('git remote get-url origin')
    return jsonify({'remote_url': url if rc == 0 else ''})


@api_bp.route('/update/remote', methods=['PUT'])
@token_required
def update_remote_set(current_user):
    from app.updater import set_remote, ensure_repo
    data = request.get_json(silent=True) or {}
    url = (data.get('remote_url') or '').strip()
    if not url:
        return jsonify({'message': 'remote_url required'}), 400
    ensure_repo()
    set_remote(url)
    return jsonify({'message': 'ok', 'remote_url': url})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _asset_dict(asset, domain_name: str = '') -> dict:
    return {
        'id': asset.id,
        'subdomain': asset.subdomain,
        'domain': domain_name,
        'ip_addresses': asset.ip_addresses,
        'source': asset.source,
        'first_seen': asset.first_seen.isoformat(),
        'last_seen': asset.last_seen.isoformat(),
        'is_new': asset.is_new,
    }
