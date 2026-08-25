import concurrent.futures
from datetime import datetime, timezone
import requests
import dns.resolver
from app import db
from app.models import Asset, ScanLog

COMMON_SUBS = [
    'www', 'mail', 'api', 'dev', 'staging', 'test', 'admin', 'portal',
    'blog', 'shop', 'cdn', 'static', 'assets', 'media', 'docs', 'help',
    'support', 'status', 'monitor', 'metrics', 'log', 'logs', 'analytics',
    'app', 'm', 'mobile', 'secure', 'vpn', 'remote', 'gateway', 'beta',
    'demo', 'backup', 'ns1', 'ns2', 'dns', 'smtp', 'imap', 'ftp', 'ssh',
    'git', 'jenkins', 'ci', 'jira', 'wiki', 'ldap', 'auth', 'sso', 'login',
    'oauth', 'account', 'billing', 'pay', 'store', 'crm', 'hr', 'internal',
    'corp', 'partner', 'news', 'forum', 'community', 'kb', 'learn', 'train',
    'event', 'career', 'job', 'about', 'contact', 'press', 'investor',
    'trust', 'safety', 'policy', 'terms', 'privacy', 'sitemap', 'robots',
    'chat', 'messenger', 'notify', 'push', 'ws', 'socket', 'realtime',
    'upload', 'download', 'files', 'storage', 'bucket', 's3', 'objects',
    'k8s', 'kubernetes', 'docker', 'registry', 'packages', 'repo',
    'grafana', 'prometheus', 'alert', 'alerts', 'kibana', 'elastic',
    'kafka', 'rabbitmq', 'redis', 'mongo', 'db', 'database', 'sql',
    'bastion', 'jump', 'proxy', 'lb', 'load', 'fe', 'be', 'backend',
    'frontend', 'web', 'app1', 'app2', 'srv1', 'srv2', 'node1', 'node2',
    'dc1', 'dc2', 'az1', 'az2', 'cluster', 'master', 'slave', 'worker',
    'open', 'public', 'private', 'int', 'ext', 'edge', 'origin',
    'sandbox', 'lab', 'labs', 'research', 'rd', 'eng', 'engineering',
    'console', 'mgmt', 'manage', 'management', 'panel', 'cp', 'control',
]


def _query_crtsh(domain: str) -> set:
    subs = set()
    try:
        resp = requests.get(
            f'https://crt.sh/?q=%25.{domain}&output=json',
            timeout=30,
            headers={'User-Agent': 'Mozilla/5.0'},
        )
        if resp.status_code == 200:
            for entry in resp.json():
                name = entry.get('name_value', '')
                for n in name.split('\n'):
                    n = n.strip().lower().replace('*.', '')
                    if n.endswith(f'.{domain}') or n == domain:
                        subs.add(n)
    except Exception:
        pass
    return subs


def _query_alienvault(domain: str) -> set:
    subs = set()
    try:
        resp = requests.get(
            f'https://otx.alienvault.com/api/v1/indicators/domain/{domain}/passive_dns',
            timeout=20,
            headers={'User-Agent': 'Mozilla/5.0'},
        )
        if resp.status_code == 200:
            for entry in resp.json().get('passive_dns', []):
                hostname = entry.get('hostname', '').strip().lower()
                if hostname.endswith(f'.{domain}') or hostname == domain:
                    subs.add(hostname)
    except Exception:
        pass
    return subs


def _resolve(subdomain: str) -> str:
    ips = set()
    for rtype in ('A', 'AAAA'):
        try:
            answers = dns.resolver.resolve(subdomain, rtype, lifetime=3)
            for rdata in answers:
                ips.add(str(rdata))
        except Exception:
            pass
    return ','.join(sorted(ips)) if ips else ''


def _dns_bruteforce(domain: str) -> set:
    found = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
        futures = {}
        for sub in COMMON_SUBS:
            fqdn = f'{sub}.{domain}'
            futures[ex.submit(_resolve, fqdn)] = fqdn
        for future in concurrent.futures.as_completed(futures, timeout=30):
            fqdn = futures[future]
            try:
                if future.result():
                    found.add(fqdn)
            except Exception:
                pass
    return found


def scan_domain(domain_obj) -> tuple:
    """Run a full scan. Returns (new_count, all_subs_list)."""
    log = ScanLog(domain_id=domain_obj.id, status='running')
    db.session.add(log)
    db.session.commit()

    all_subs: set = set()

    all_subs.update(_query_crtsh(domain_obj.domain))
    all_subs.update(_query_alienvault(domain_obj.domain))
    all_subs.update(_dns_bruteforce(domain_obj.domain))

    new_count = 0
    now = datetime.now(timezone.utc)
    for sub in all_subs:
        if len(sub) > 512:
            continue
        existing = Asset.query.filter_by(
            domain_id=domain_obj.id, subdomain=sub,
        ).first()
        if existing:
            existing.last_seen = now
        else:
            ips = _resolve(sub)
            db.session.add(Asset(
                domain_id=domain_obj.id,
                subdomain=sub,
                ip_addresses=ips,
                source='passive',
                is_new=True,
            ))
            new_count += 1

    domain_obj.last_scan_at = now
    log.finished_at = now
    log.assets_found = len(all_subs)
    log.new_assets_found = new_count
    log.status = 'completed'
    db.session.commit()

    return new_count, list(all_subs)
