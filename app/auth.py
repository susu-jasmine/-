import functools
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from app import db
from app.models import User
from config import Config

auth_bp = Blueprint('auth', __name__)

_login_attempts: dict = {}


def token_required(f):
    @functools.wraps(f)
    def decorator(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization', '')
        parts = auth_header.split()
        if len(parts) == 2 and parts[0] == 'Bearer':
            token = parts[1]

        if not token:
            return jsonify({'error': 'Token required'}), 401

        try:
            data = jwt.decode(token, Config.SECRET_KEY, algorithms=['HS256'])
            current_user = db.session.get(User, data['user_id'])
            if not current_user:
                return jsonify({'error': 'User not found'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401

        return f(current_user, *args, **kwargs)
    return decorator


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    ip = request.remote_addr or '127.0.0.1'
    key = f'{ip}:{username}'
    attempt = _login_attempts.get(key, {'count': 0, 'since': datetime.now(timezone.utc)})

    if attempt['count'] >= Config.LOGIN_MAX_ATTEMPTS:
        elapsed = (datetime.now(timezone.utc) - attempt['since']).total_seconds()
        if elapsed < Config.LOGIN_LOCKOUT_MINUTES * 60:
            return jsonify({'error': 'Too many attempts. Try later.'}), 429
        _login_attempts.pop(key, None)

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        attempt['count'] = attempt.get('count', 0) + 1
        if attempt['count'] == 1:
            attempt['since'] = datetime.now(timezone.utc)
        _login_attempts[key] = attempt
        return jsonify({'error': 'Invalid credentials'}), 401

    _login_attempts.pop(key, None)
    token = _make_token(user.id)
    return jsonify({'token': token, 'user': {'id': user.id, 'username': user.username}})


@auth_bp.route('/me', methods=['GET'])
@token_required
def me(current_user):
    return jsonify({
        'id': current_user.id,
        'username': current_user.username,
        'email': current_user.email,
        'pushplus_token': (
            '***' + current_user.pushplus_token[-4:]
            if current_user.pushplus_token else ''
        ),
        'smtp_host': current_user.smtp_host,
        'smtp_user': current_user.smtp_user,
        'smtp_from': current_user.smtp_from,
        'notify_email': current_user.notify_email,
        'notify_wechat': current_user.notify_wechat,
        'src_interval_hours': current_user.src_interval_hours,
        'bountyteam_token': (
            '***' + current_user.bountyteam_token[-4:]
            if current_user.bountyteam_token else ''
        ),
        'bountyteam_interval_minutes': current_user.bountyteam_interval_minutes,
        'bountyteam_auto_apply': bool(current_user.bountyteam_auto_apply),
        'bountyteam_fast_poll': bool(current_user.bountyteam_fast_poll),
        'bountyteam_poll_seconds': current_user.bountyteam_poll_seconds or 3,
        # 360 众测 (cookie 脱敏显示)
        'zc_cookie': (
            '***' + current_user.zc_cookie[-6:]
            if current_user.zc_cookie else ''
        ),
        'zc_interval_seconds': current_user.zc_interval_seconds or 3,
        'zc_auto_apply': bool(current_user.zc_auto_apply),
        'zc_fast_poll': bool(current_user.zc_fast_poll),
        # 补天/漏洞盒子 秒级
        'src_fast_poll': bool(current_user.src_fast_poll),
        'src_poll_seconds': current_user.src_poll_seconds or 5,
    })


def _make_token(user_id: int) -> str:
    return jwt.encode(
        {
            'user_id': user_id,
            'exp': datetime.now(timezone.utc)
            + timedelta(hours=Config.JWT_EXPIRATION_HOURS),
        },
        Config.SECRET_KEY,
        algorithm='HS256',
    )
