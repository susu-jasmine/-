"""Online updater — git pull + pip install + systemd restart."""
import os, subprocess

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
VENV_PYTHON = os.path.join(APP_DIR, 'venv', 'bin', 'python')


def _run(cmd: str, timeout: int = 60):
    try:
        r = subprocess.run(
            cmd, shell=True, cwd=APP_DIR,
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, '', 'timeout'


def _detect_branch() -> str:
    rc, out, _ = _run('git rev-parse --abbrev-ref HEAD')
    if rc == 0 and out:
        return out.strip()
    return 'main'


def ensure_repo():
    if not os.path.exists(os.path.join(APP_DIR, '.git')):
        _run('git init -q')
        _run('git config user.email "asset@local"')
        _run('git config user.name "asset-monitor"')
        _run('git config advice.detachedHead false')
        return False
    return True


def set_remote(url: str):
    rc, _, _ = _run('git remote get-url origin')
    if rc == 0:
        _run(f'git remote set-url origin {url}')
    else:
        _run(f'git remote add origin {url}')


def check_for_updates():
    ensure_repo()
    rc, _, remote_url = _run('git remote get-url origin')
    if rc != 0 or not remote_url:
        return {'error': 'no_remote', 'has_update': False,
                'hint': '请先在设置中配置 Git 仓库地址'}

    rc, _, err = _run('git fetch origin --tags --force', timeout=120)
    if rc != 0:
        return {'error': 'fetch_failed', 'has_update': False, 'detail': err}

    branch = _detect_branch()
    rc, local, _ = _run('git rev-parse HEAD')
    rc2, remote, _ = _run(f'git rev-parse origin/{branch}')
    if rc2 != 0:
        for b in ('main', 'master'):
            rc2, remote, _ = _run(f'git rev-parse origin/{b}')
            if rc2 == 0:
                branch = b
                break
    if rc2 != 0:
        return {'error': 'no_remote_branch', 'has_update': False}

    has_update = local.strip() != remote.strip()
    payload = {
        'has_update': has_update,
        'current': (local or '')[:8],
        'remote': (remote or '')[:8],
        'branch': branch,
        'remote_url': remote_url,
    }
    if has_update:
        rc, log, _ = _run(
            f'git log --pretty=format:"%h|%s|%an|%ci" {local}..{remote}'
        )
        commits = []
        for line in (log or '').splitlines():
            parts = line.strip().strip('"').split('|')
            if len(parts) >= 4:
                commits.append({
                    'hash': parts[0], 'subject': parts[1],
                    'author': parts[2], 'date': parts[3][:16],
                })
        payload['commits'] = commits
        payload['behind'] = len(commits)
    return payload


def apply_update():
    ensure_repo()
    info = check_for_updates()
    if info.get('error'):
        return False, info.get('detail') or info.get('hint') or info['error']
    if not info.get('has_update'):
        return True, 'already_latest'

    branch = info['branch']
    rc, out, err = _run(f'git pull origin {branch} --ff-only', timeout=180)
    if rc != 0:
        return False, f'pull failed: {err or out}'

    rc, out, err = _run(
        f'{VENV_PYTHON} -m pip install -r requirements.txt -q', timeout=300
    )

    # Run db migration (idempotent)
    try:
        subprocess.run(
            [VENV_PYTHON, '-c',
             'import sqlite3,os; from app import create_app, db; '
             'create_app(); print("ok")'],
            cwd=APP_DIR, capture_output=True, text=True, timeout=60,
        )
    except Exception:
        pass

    # Trigger systemd restart via sudoers rule (detached so request completes)
    subprocess.Popen(
        ['bash', '-c',
         'sleep 1.5 && sudo -n /bin/systemctl restart asset-monitor'],
        cwd=APP_DIR,
    )
    return True, 'restarting'
