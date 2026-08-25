#!/usr/bin/env bash
set -euo pipefail
# ============================================================================
# AssetMonitor // 一键部署脚本 (Linux)
# Usage: chmod +x deploy.sh && sudo ./deploy.sh
# 可选: sudo DOMAIN=srchunt.com APP_PORT=8080 ./deploy.sh
# 可选: sudo WEB_WORKERS=1 UPDATE_REPO=https://github.com/xxx/asset-monitor.git ./deploy.sh
#
# v1.1 新增: 雷神众测 (BountyTeam) 抢名额监控 + Token 滑动续期保活
#   - 自动迁移 users 表 (bountyteam_token / bountyteam_interval_minutes)
#   - bounty_projects 表由 create_all 自动创建
#   - 后台: 域名扫描 / SRC扫描 / 雷神众测扫描(3min) / 保活心跳(30min)
# ============================================================================

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${RED}[!]${NC} $*"; }

APP_DIR="/opt/asset-monitor"
APP_USER="assetmonitor"
APP_PORT="${APP_PORT:-5000}"
WEB_WORKERS="${WEB_WORKERS:-1}"
SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"
DOMAIN="${DOMAIN:-}"
LISTEN_IP="${LISTEN_IP:-0.0.0.0}"

case "$WEB_WORKERS" in
    ''|*[!0-9]*) warn "WEB_WORKERS 必须是正整数"; exit 1 ;;
    0) warn "WEB_WORKERS 必须大于 0"; exit 1 ;;
esac

[ "$(id -u)" -ne 0 ] && { warn "请用 root 运行: sudo ./deploy.sh"; exit 1; }

# ====== 依赖 ======
log "安装系统依赖..."
if command -v apt &>/dev/null; then
    apt update -qq && apt install -y -qq python3 python3-pip python3-venv curl 2>/dev/null
else
    yum install -y -q python3 python3-pip python3-virtualenv curl 2>/dev/null || \
    dnf install -y -q python3 python3-pip python3-virtualenv curl 2>/dev/null
fi

# ====== 用户 ======
id -u "$APP_USER" &>/dev/null || useradd -r -s /bin/false "$APP_USER"

# ====== 代码 ======
log "部署代码到 $APP_DIR"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$APP_DIR" "$APP_DIR/data" "$APP_DIR/logs"
# 用 rsync 优先, 排除本地构建产物/缓存/venv; 退化为 tar
if command -v rsync &>/dev/null; then
    rsync -a --delete \
        --exclude='venv/' --exclude='__pycache__/' --exclude='*.pyc' \
        --exclude='.git/' --exclude='data/monitor.db' --exclude='logs/' \
        --exclude='.env' --exclude='node_modules/' \
        "$SRC_DIR/" "$APP_DIR/"
else
    ( cd "$SRC_DIR" && tar --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='.git' --exclude='data/monitor.db' --exclude='logs' --exclude='.env' \
        -cf - . ) | ( cd "$APP_DIR" && tar -xf - )
fi
# 确保新增模块存在 (部署自检)
for f in app/bountyteam_monitor.py; do
    [ -f "$APP_DIR/$f" ] || warn "缺失文件: $f (可能拷贝被排除, 请检查)"
done

# ====== 权限 ======
log "修正权限..."
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod 755 "$APP_DIR" "$APP_DIR/data" "$APP_DIR/logs"
find "$APP_DIR/data" -type f -exec chmod 644 {} \; 2>/dev/null || true

# ====== Python venv ======
log "创建虚拟环境..."
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
deactivate
chown -R "$APP_USER:$APP_USER" "$APP_DIR/venv"

# ====== Git 仓库 (用于在线更新) ======
log "初始化 Git 仓库..."
if ! command -v git &>/dev/null; then
    if command -v apt-get &>/dev/null; then
        apt-get update -qq >/dev/null 2>&1 || true
        apt-get install -y -qq git >/dev/null 2>&1 || true
    elif command -v dnf &>/dev/null; then
        dnf install -y -q git >/dev/null 2>&1 || true
    elif command -v yum &>/dev/null; then
        yum install -y -q git >/dev/null 2>&1 || true
    else
        warn "未找到可用的包管理器，将跳过 Git 初始化"
    fi
fi

# Git 不是本次服务启动的硬依赖。仓库损坏/权限异常时跳过 Git，继续完成部署。
GIT_READY=0
if command -v git &>/dev/null; then
    # root 运行脚本时，目标目录通常属于 assetmonitor，Git 会触发 dubious ownership。
    GIT_SAFE=(git -c "safe.directory=$APP_DIR" -C "$APP_DIR")

    if ! "${GIT_SAFE[@]}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        if [ -e "$APP_DIR/.git" ]; then
            backup_git="$APP_DIR/.git.deploy-backup.$(date +%Y%m%d%H%M%S)"
            if mv "$APP_DIR/.git" "$backup_git"; then
                warn "检测到无效 .git，已备份到 $backup_git"
            else
                warn "无法备份无效 .git，将跳过 Git 初始化"
            fi
        fi
        if git init -q "$APP_DIR" 2>/dev/null && \
           "${GIT_SAFE[@]}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
            GIT_READY=1
        else
            warn "Git 仓库初始化失败，将跳过 Git；不影响 Web 服务安装"
        fi
    else
        GIT_READY=1
    fi

    if [ "$GIT_READY" -eq 1 ]; then
        # 配置本地仓库；Git 已确认可用。
        "${GIT_SAFE[@]}" config --local user.email "$("${GIT_SAFE[@]}" config --local user.email 2>/dev/null || printf '%s' 'asset@local')"
        "${GIT_SAFE[@]}" config --local user.name "$("${GIT_SAFE[@]}" config --local user.name 2>/dev/null || printf '%s' 'asset-monitor')"
        "${GIT_SAFE[@]}" config --local advice.detachedHead false
        "${GIT_SAFE[@]}" add -A
        "${GIT_SAFE[@]}" commit -qm "initial deploy" || true
        # 在线更新由 assetmonitor 用户执行，所以 .git 也必须归该用户所有。
        chown -R "$APP_USER:$APP_USER" "$APP_DIR/.git" 2>/dev/null || true

        if [ -n "${UPDATE_REPO:-}" ]; then
            "${GIT_SAFE[@]}" remote remove origin 2>/dev/null || true
            "${GIT_SAFE[@]}" remote add origin "$UPDATE_REPO"
            log "已配置远端: $UPDATE_REPO"
        fi
    fi
else
    warn "未安装 Git，将跳过 Git 初始化；不影响 Web 服务安装"
fi

# ====== sudoers: 允许 assetmonitor 重启服务 ======
log "配置 sudoers 规则..."
cat > /etc/sudoers.d/asset-monitor <<EOF
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl restart asset-monitor
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl reload asset-monitor
EOF
chmod 440 /etc/sudoers.d/asset-monitor
visudo -cf /etc/sudoers.d/asset-monitor 2>/dev/null || true

# ====== 环境变量 ======
cat > "$APP_DIR/.env" <<EOF
SECRET_KEY=$SECRET_KEY
JWT_EXPIRATION_HOURS=168
EOF
chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

# ====== 升级迁移 (必须在 create_app 之前) ======
log "检查数据库迁移..."
cd "$APP_DIR"
python3 <<'PYEOF'
import sqlite3, os
db_path = os.path.abspath('data/monitor.db')
if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        for table, col, coltype in [
            ('domains', 'organization', 'VARCHAR(128) DEFAULT ""'),
            ('users', 'src_interval_hours', 'INTEGER DEFAULT 1'),
            ('users', 'notify_wechat', 'INTEGER DEFAULT 1'),
            # v1.1 雷神众测监控
            ('users', 'bountyteam_token', 'VARCHAR(128) DEFAULT ""'),
            ('users', 'bountyteam_interval_minutes', 'INTEGER DEFAULT 3'),
            # v1.2 自动报名
            ('users', 'bountyteam_auto_apply', 'BOOLEAN DEFAULT 0'),
            # v1.3 极速轮询 (秒级)
            ('users', 'bountyteam_fast_poll', 'BOOLEAN DEFAULT 0'),
            ('users', 'bountyteam_poll_seconds', 'INTEGER DEFAULT 3'),
            # v1.4 360众测 + 补天/漏洞盒子秒级
            ('users', 'zc_cookie', 'VARCHAR(2048) DEFAULT ""'),
            ('users', 'zc_interval_seconds', 'INTEGER DEFAULT 3'),
            ('users', 'zc_auto_apply', 'BOOLEAN DEFAULT 0'),
            ('users', 'zc_fast_poll', 'BOOLEAN DEFAULT 0'),
            ('users', 'src_poll_seconds', 'INTEGER DEFAULT 5'),
            ('users', 'src_fast_poll', 'BOOLEAN DEFAULT 0'),
            ('bounty_projects', 'apply_status', 'VARCHAR(16) DEFAULT ""'),
            ('bounty_projects', 'apply_time', 'DATETIME'),
            ('bounty_projects', 'apply_err', 'VARCHAR(256) DEFAULT ""'),
        ]:
            try:
                cur = conn.execute(f"PRAGMA table_info({table})")
                cols = [r[1] for r in cur.fetchall()]
                if col not in cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
                    conn.commit()
                    print(f'[MIGRATE] 已添加 {table}.{col}')
            except Exception as e:
                print(f'[MIGRATE] {table}.{col} 跳过:', e)
        # bounty_projects 表由 create_all 创建(SQLAlchemy);此处仅补列
        conn.close()
        print('[MIGRATE] 数据库迁移完成')
    except Exception as e:
        print('[MIGRATE] 跳过:', e)
else:
    print('[MIGRATE] 数据库不存在，将由 create_all 创建')
PYEOF

# ====== 初始化 DB ======
log "初始化数据库..."
source venv/bin/activate
# 以服务用户身份初始化 DB，避免生成的 data/monitor.db 归属 root 导致后续写入失败
su -s /bin/bash "$APP_USER" -c "
cd '$APP_DIR'
'$APP_DIR/venv/bin/python' <<'PYEOF'
from app import create_app, db
from app.models import User, Domain
from werkzeug.security import generate_password_hash

app = create_app()
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(username='admin',
            password_hash=generate_password_hash('admin123456'),
            src_interval_hours=1, notify_wechat=True,
            bountyteam_interval_minutes=3))
        db.session.commit()
        print('[OK] 管理员: admin / admin123456')
    else:
        print('[OK] 管理员已存在')
PYEOF
"
deactivate
# 再次确保 data/ 目录及其下所有文件归服务用户所有（覆盖旧库归属、WAL/SHM 文件等）
chown -R "$APP_USER:$APP_USER" "$APP_DIR/data"
chmod 755 "$APP_DIR/data"
find "$APP_DIR/data" -type f -exec chmod 644 {} \; 2>/dev/null || true

# ====== systemd 服务 ======
log "创建 systemd 服务..."
cat > /etc/systemd/system/asset-monitor.service <<EOF
[Unit]
Description=Asset Monitor
After=network.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/gunicorn -w $WEB_WORKERS -b ${LISTEN_IP}:${APP_PORT} --timeout 120 --access-logfile $APP_DIR/logs/access.log --error-logfile $APP_DIR/logs/error.log run:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable asset-monitor
systemctl restart asset-monitor

sleep 2
if ! systemctl is-active --quiet asset-monitor; then
    warn "=== 启动失败 ==="
    tail -15 "$APP_DIR/logs/error.log" 2>/dev/null || true
    journalctl -u asset-monitor -n 10 --no-pager
    echo ""
    warn "常见修复: chown -R $APP_USER:$APP_USER $APP_DIR && systemctl restart asset-monitor"
    exit 1
fi
log "服务运行中 OK"

# ====== Nginx ======
if [ -n "$DOMAIN" ]; then
    log "配置 Nginx: $DOMAIN"
    apt install -y -qq nginx 2>/dev/null || yum install -y -q nginx 2>/dev/null || true
    cat > "/etc/nginx/sites-available/asset-monitor" <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    client_max_body_size 10m;
    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }
}
EOF
    ln -sf /etc/nginx/sites-available/asset-monitor /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    nginx -t && systemctl reload nginx
    log "Nginx OK → http://$DOMAIN"
fi

# ====== 防火墙 ======
ufw disable 2>/dev/null || true
systemctl stop firewalld 2>/dev/null || true
iptables -P INPUT ACCEPT 2>/dev/null || true
iptables -F 2>/dev/null || true

# ====== 完成 ======
IP=$(hostname -I 2>/dev/null | awk '{print $1}') || IP="服务器IP"
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  AssetMonitor 部署成功${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "  ${CYAN}http://${IP}:${APP_PORT}${NC}"
[ -n "$DOMAIN" ] && echo -e "  ${CYAN}http://${DOMAIN}${NC}"
echo ""
echo -e "  账户  ${CYAN}admin${NC}"
echo -e "  密码  ${CYAN}admin123456${NC}"
echo ""
echo -e "  ${GREEN}登录后立即修改密码！${NC}"
echo ""
echo -e "  ${CYAN}雷神众测监控:${NC} 登录后进「设置→雷神众测监控」填入 BountyTeam Token"
echo -e "  ${CYAN}         (登录 bountyteam.com 后控制台执行 localStorage.getItem(\"jwtToken\"))${NC}"
echo -e "  ${CYAN}         并在「微信推送」填入 PushPlus Token 以接收抢名额通知${NC}"
echo ""
echo -e "  ${CYAN}Web workers: ${WEB_WORKERS} (SQLite + APScheduler 默认单 worker)${NC}"
echo -e "  ${RED}云服务器别忘了去控制台安全组放行 ${APP_PORT} 端口${NC}"
