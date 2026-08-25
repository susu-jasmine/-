/* ================================================================
   AssetMonitor // i18n Bilingual Support (zh / en)
   ================================================================ */
const I18N = (function() {
  'use strict';

  const translations = {
    zh: {
      // ---- Login Page ----
      login_title: '资产监控 // 访问',
      dashboard_title: '资产监控 // 仪表盘',
      login_sub: 'v1.0 // 资产监控系统',
      login_username: '用户名',
      login_password: '密码',
      login_passphrase: '密码',
      login_btn: '验证_',
      login_first_time: '首次使用?',
      login_create_account: '创建账户',
      login_reg_title: '新账户',
      login_reg_username_ph: '至少4位',
      login_reg_password_ph: '至少8位',
      login_reg_email_ph: 'user@example.com',
      login_reg_email_label: 'Email (可选, 用于邮件通知)',
      login_reg_create: '创建',
      login_reg_cancel: '取消',
      login_err_empty: '> 请输入用户名和密码',
      login_err_auth: '> 验证中...',
      login_err_create: '> 创建中...',
      login_err_net: '> 网络错误: ',
      login_err_username_short: '> 用户名至少3位',
      login_err_password_short: '> 密码至少8位',

      // ---- Dashboard Nav ----
      nav_domains: '域名',
      nav_assets: '全部资产',
      nav_logs: '扫描日志',
      nav_settings: '设置',
      nav_logout: '[ 登出 ]',

      // ---- Stats ----
      stat_domains: '域名',
      stat_total: '总资产',
      stat_new: '新资产',
      stat_today: '今日发现',

      // ---- Domain Section ----
      domain_title: '// 域名管理',
      domain_input_ph: 'example.com',
      domain_interval: '扫描间隔(h)',
      domain_add_btn: '添加域名',
      domain_th_domain: '域名',
      domain_th_status: '状态',
      domain_th_assets: '资产',
      domain_th_new: '新增',
      domain_th_interval: '间隔',
      domain_th_scan: '上次扫描',
      domain_th_actions: '操作',
      domain_empty: '暂无监控域名，请添加',
      domain_org_ph: '所属单位 (可选)',
      domain_org_label: '所属单位',
      domain_batch_btn: '批量导入',
      domain_batch_label: '域名列表 (每行一个)',
      domain_batch_run: '执行导入',
      domain_interval_label: '扫描间隔(h)',
      domain_filter_org: '筛选单位:',
      domain_th_org: '单位',

      // ---- Domain Actions ----
      act_pause: '暂停',
      act_resume: '恢复',
      act_scan: '扫描',
      act_edit: '编辑',
      act_del: '删除',

      // ---- Status ----
      status_active: '活跃',
      status_paused: '已暂停',
      status_new: '新',
      status_seen: '已读',
      status_running: '运行中',
      status_completed: '完成',
      status_failed: '失败',

      // ---- Asset Section ----
      asset_title: '// 全部资产',
      asset_search_ph: '搜索子域名...',
      asset_new_only: '仅新资产',
      asset_mark_all: '全部标记已读',
      asset_export_csv: '导出CSV',
      asset_export_json: '导出JSON',
      asset_th_sub: '子域名',
      asset_th_root: '根域名',
      asset_th_ip: 'IP',
      asset_th_source: '来源',
      asset_th_first: '首次发现',
      asset_th_status: '状态',
      asset_th_action: '操作',
      asset_empty: '未发现资产',

      // ---- Pagination ----
      pager_prev: '上一页',
      pager_next: '下一页',
      pager_total: '总计',

      // ---- Scan Logs ----
      log_title: '// 扫描日志',
      log_th_domain: '域名',
      log_th_started: '开始时间',
      log_th_finished: '结束时间',
      log_th_found: '发现',
      log_th_new: '新增',
      log_th_status: '状态',
      log_empty: '暂无日志',

      // ---- Settings ----
      settings_title: '// 通知设置',
      settings_pushplus_title: '微信推送 (PushPlus)',
      settings_pushplus_hint: '关注 PushPlus 公众号获取 token → pushplus.plus',
      settings_pushplus_label: 'PushPlus Token',
      settings_pushplus_ph: '你的32位token',
      settings_wechat_enable: '启用微信推送',

      settings_email_title: '邮件通知',
      settings_email_label: 'Email',
      settings_email_ph: 'you@example.com',
      settings_smtp_host: 'SMTP 服务器',
      settings_smtp_port: 'SMTP 端口',
      settings_smtp_user: 'SMTP 用户名',
      settings_smtp_pass: 'SMTP 密码(授权码)',
      settings_smtp_from: '发件人地址',
      settings_email_enable: '启用邮件通知',

      settings_save_btn: '保存设置',
      settings_saved: '> 设置已保存。',
      settings_failed: '> 保存失败。',
      settings_src_title: 'SRC监控频率',
      settings_src_interval: '扫描间隔 (小时)',

      update_title: '// 在线更新',
      update_repo_label: 'Git 仓库地址',
      update_repo_ph: 'https://github.com/user/repo.git',
      update_save_repo: '保存仓库',
      update_check_btn: '检查更新',
      update_apply_btn: '应用更新',
      update_checking: '> 正在检查更新...',
      update_no_remote: '> 请先填写并保存 Git 仓库地址',
      update_latest: '> 已是最新版本',
      update_found: '> 发现新版本，落后 ',
      update_commits: ' 个提交',
      update_applying: '> 正在应用更新，服务将在 5 秒后重启...',
      update_done: '> 更新完成，正在刷新页面...',
      update_failed: '> 更新失败: ',
      update_repo_saved: '> 仓库地址已保存',
      update_confirm: '确定应用更新? 服务将短暂中断 3-5 秒',
      update_branch: '分支',
      update_current: '当前',
      update_remote: '远端',
      update_no_update_info: '> 暂无更新信息',

      nav_src: 'SRC监控',
      stat_src_new: 'SRC新企业',
      src_title: '// SRC平台监控',
      src_scan_now: '立即扫描',
      src_search_ph: '搜索企业...',
      src_all_platforms: '全部平台',
      src_th_platform: '平台',
      src_th_company: '企业',
      src_th_reward: '奖金范围',
      src_th_desc: '描述',
      src_th_update: '更新时间',
      src_th_status: '状态',
      src_empty: '暂无数据，点击"立即扫描"开始',

      // ---- BountyTeam ----
      bounty_title: '// 雷神众测 · 抢名额监控',
      bounty_scan_now: '立即扫描',
      bounty_search_ph: '搜索项目...',
      bounty_open_only: '仅可报名',
      bounty_new_only: '仅新增',
      bounty_mark_all: '全部标记已读',
      bounty_th_name: '项目',
      bounty_th_reward: '奖金(元)',
      bounty_th_remain: '剩余名额',
      bounty_th_surplus: '剩余天数',
      bounty_th_state: '状态',
      bounty_th_seen: '状态',
      bounty_th_action: '操作',
      bounty_empty: '暂无可报名项目，等待监控抓取...',
      bounty_apply: '去报名',
      bounty_state_apply: '报名中',
      bounty_state_doing: '进行中',
      bounty_state_pause: '暂停中',
      bounty_state_stop: '已结束',
      bounty_closed: '已关闭',
      bounty_open: '可报名',
      bounty_th_apply_status: '报名',
      bounty_applied: '已自动报名',
      bounty_apply_failed: '报名失败',
      bounty_retry_apply: '重试报名',
      bounty_apply_ok: '报名成功',
      bounty_auto_apply: '自动报名 (检测到新项目立即调用平台报名接口)',
      bounty_auto_apply_hint: '用你的账号对每个新检测到的可报名项目自动点击报名；失败原因会推送到微信/邮件。需账号已完成实名/认证，否则平台会拒绝。',
      bounty_fast_poll: '极速模式 (秒级轮询)',
      bounty_fast_poll_hint: '用独立守护线程按秒级间隔扫描并立即报名。间隔越小越快，但持续高频请求可能触发平台风控限流/封禁，建议 2-3 秒。关闭后恢复分钟级扫描。',
      bounty_poll_seconds: '极速轮询间隔 (秒, 1-60)',
      bounty_interval: '扫描间隔 (分钟, 1-60)',
      bounty_token_title: '雷神众测 (BountyTeam)',
      bounty_token_label: 'BountyTeam Token (jwtToken)',
      bounty_token_hint: '登录 bountyteam.com 后，浏览器控制台执行 localStorage.getItem("jwtToken") 复制值',
      settings_bounty_title: '雷神众测监控',

      // ---- 360众测 ----
      zc_title: '360众测',
      zc_settings_title: '360众测监控',
      zc_scan_now: '立即扫描',
      zc_search_ph: '搜索项目...',
      zc_open_only: '仅开放',
      zc_new_only: '仅新增',
      zc_mark_all: '全部标记已读',
      zc_th_name: '项目',
      zc_th_reward: '奖金(元)',
      zc_th_surplus: '剩余天数',
      zc_th_state: '开始时间',
      zc_th_seen: '状态',
      zc_th_apply: '报名',
      zc_th_action: '操作',
      zc_empty: '暂无项目，等待监控抓取...',
      zc_open: '开放',
      zc_closed: '已关闭',
      zc_apply: '去报名',
      zc_applied: '已自动报名',
      zc_apply_failed: '报名失败',
      zc_retry_apply: '重试报名',
      zc_apply_ok: '报名成功',
      zc_cookie_label: '360众测 Cookie (完整登录 Cookie)',
      zc_cookie_hint: '浏览器登录 zhongce.360.net 后，F12 → Network → 任意请求 → 复制 Cookie 请求头的完整值（注意保持分号分隔格式）。',
      zc_interval: '轮询间隔 (秒, 1-60)',
      zc_auto_apply: '自动报名',
      zc_auto_apply_hint: '检测到新项目立即调用报名接口。需账号完成实名认证+完善资料+签署保密协议+技术考核，否则平台会拒绝。',
      zc_fast_poll: '极速模式 (秒级轮询)',

      // ---- SRC 秒级 ----
      src_settings_title: 'SRC监控 (补天/漏洞盒子)',
      src_fast_poll: '秒级轮询',
      src_fast_poll_hint: '以秒级间隔扫描补天和漏洞盒子，发现新企业/新项目立即通知。默认 5 秒，间隔越小越快但高频请求可能触发限流。',
      src_poll_seconds: '轮询间隔 (秒, 1-60)',

      // ---- Toast ----
      toast_paused: '已暂停',
      toast_resumed: '已恢复',
      toast_scanning: '扫描中...',
      toast_scan_done: '扫描完成: ',
      toast_assets: ' 个资产, ',
      toast_new: ' 个新增',
      toast_deleted: '已删除',
      toast_domain_empty: '请输入域名',
      toast_added: '已添加: ',
      toast_assets_found: ' 个资产',
      toast_marked: '已全部标记为已读',
      toast_settings_saved: '设置已保存',
      toast_failed: '失败',

      // ---- Confirm ----
      confirm_delete: '确定删除此域名及所有资产?',

      // ---- Time ----
      time_never: '从未',

      // ---- Misc ----
      brand: '资产监控系统',
    },

    en: {
      // ---- Login Page ----
      login_title: 'Asset Monitor // Access',
      dashboard_title: 'Asset Monitor // Dashboard',
      login_sub: 'v1.0 // Asset Monitoring System',
      login_username: 'Username',
      login_password: 'Password',
      login_passphrase: 'Passphrase',
      login_btn: 'AUTHENTICATE_',
      login_first_time: 'First time?',
      login_create_account: 'Create account',
      login_reg_title: 'New Account',
      login_reg_username_ph: 'At least 3 chars',
      login_reg_password_ph: 'At least 8 chars',
      login_reg_email_ph: 'user@example.com',
      login_reg_email_label: 'Email (optional, for notifications)',
      login_reg_create: 'Create',
      login_reg_cancel: 'Cancel',
      login_err_empty: '> Username and password required',
      login_err_auth: '> Authenticating...',
      login_err_create: '> Creating...',
      login_err_net: '> Network error: ',
      login_err_username_short: '> Username must be at least 3 chars',
      login_err_password_short: '> Password must be at least 8 chars',

      // ---- Dashboard Nav ----
      nav_domains: 'Domains',
      nav_assets: 'All Assets',
      nav_logs: 'Scan Logs',
      nav_settings: 'Settings',
      nav_logout: '[ Logout ]',

      // ---- Stats ----
      stat_domains: 'Domains',
      stat_total: 'Total Assets',
      stat_new: 'New Assets',
      stat_today: 'Today Discovered',

      // ---- Domain Section ----
      domain_title: '// Domain Management',
      domain_input_ph: 'example.com',
      domain_interval: 'Interval (h)',
      domain_add_btn: 'ADD DOMAIN',
      domain_th_domain: 'Domain',
      domain_th_status: 'Status',
      domain_th_assets: 'Assets',
      domain_th_new: 'New',
      domain_th_interval: 'Interval',
      domain_th_scan: 'Last Scan',
      domain_th_actions: 'Actions',
      domain_empty: 'No domains monitored. Add one above.',
      domain_org_ph: 'Organization (optional)',
      domain_org_label: 'Organization',
      domain_batch_btn: 'Batch Import',
      domain_batch_label: 'Domains (one per line)',
      domain_batch_run: 'Import',
      domain_interval_label: 'Interval (h)',
      domain_filter_org: 'Filter by org:',
      domain_th_org: 'Org',

      // ---- Domain Actions ----
      act_pause: 'PAUSE',
      act_resume: 'RESUME',
      act_scan: 'SCAN',
      act_edit: 'EDIT',
      act_del: 'DEL',

      // ---- Status ----
      status_active: 'active',
      status_paused: 'paused',
      status_new: 'NEW',
      status_seen: 'seen',
      status_running: 'running',
      status_completed: 'completed',
      status_failed: 'failed',

      // ---- Asset Section ----
      asset_title: '// All Assets',
      asset_search_ph: 'Search subdomain...',
      asset_new_only: 'New only',
      asset_mark_all: 'Mark All Seen',
      asset_export_csv: 'Export CSV',
      asset_export_json: 'Export JSON',
      asset_th_sub: 'Subdomain',
      asset_th_root: 'Root Domain',
      asset_th_ip: 'IP',
      asset_th_source: 'Source',
      asset_th_first: 'First Seen',
      asset_th_status: 'Status',
      asset_th_action: 'Action',
      asset_empty: 'No assets found.',

      // ---- Pagination ----
      pager_prev: 'Prev',
      pager_next: 'Next',
      pager_total: 'total',

      // ---- Scan Logs ----
      log_title: '// Scan Logs',
      log_th_domain: 'Domain',
      log_th_started: 'Started',
      log_th_finished: 'Finished',
      log_th_found: 'Found',
      log_th_new: 'New',
      log_th_status: 'Status',
      log_empty: 'No logs yet.',

      // ---- Settings ----
      settings_title: '// Notification Settings',
      settings_pushplus_title: 'WeChat Push (PushPlus)',
      settings_pushplus_hint: 'Follow PushPlus Official Account → pushplus.plus',
      settings_pushplus_label: 'PushPlus Token',
      settings_pushplus_ph: 'Your 32-char token',
      settings_wechat_enable: 'Enable WeChat push',

      settings_email_title: 'Email Notification',
      settings_email_label: 'Email',
      settings_email_ph: 'you@example.com',
      settings_smtp_host: 'SMTP Host',
      settings_smtp_port: 'SMTP Port',
      settings_smtp_user: 'SMTP User',
      settings_smtp_pass: 'SMTP Pass (auth code)',
      settings_smtp_from: 'From Address',
      settings_email_enable: 'Enable email notification',

      settings_save_btn: 'SAVE SETTINGS',
      settings_saved: '> Settings saved.',
      settings_failed: '> Save failed.',
      settings_src_title: 'SRC Scan Frequency',
      settings_src_interval: 'Scan Interval (hours)',

      update_title: '// Online Update',
      update_repo_label: 'Git Repository URL',
      update_repo_ph: 'https://github.com/user/repo.git',
      update_save_repo: 'Save Repo',
      update_check_btn: 'Check Update',
      update_apply_btn: 'Apply Update',
      update_checking: '> Checking for updates...',
      update_no_remote: '> Please configure Git repository URL first',
      update_latest: '> Already up to date',
      update_found: '> New version available, behind by ',
      update_commits: ' commits',
      update_applying: '> Applying update, service restarts in 5s...',
      update_done: '> Update complete, refreshing page...',
      update_failed: '> Update failed: ',
      update_repo_saved: '> Repository URL saved',
      update_confirm: 'Apply update? Service will be down for 3-5s',
      update_branch: 'Branch',
      update_current: 'Current',
      update_remote: 'Remote',
      update_no_update_info: '> No update info yet',

      nav_src: 'SRC Monitor',
      stat_src_new: 'SRC New',
      src_title: '// SRC Platform Monitor',
      src_scan_now: 'Scan Now',
      src_search_ph: 'Search company...',
      src_all_platforms: 'All Platforms',
      src_th_platform: 'Platform',
      src_th_company: 'Company',
      src_th_reward: 'Reward',
      src_th_desc: 'Description',
      src_th_update: 'Updated',
      src_th_status: 'Status',
      src_empty: 'No data. Click "Scan Now" to start.',

      // ---- BountyTeam ----
      bounty_title: '// BountyTeam · Quota Monitor',
      bounty_scan_now: 'Scan Now',
      bounty_search_ph: 'Search project...',
      bounty_open_only: 'Open only',
      bounty_new_only: 'New only',
      bounty_mark_all: 'Mark All Seen',
      bounty_th_name: 'Project',
      bounty_th_reward: 'Reward (¥)',
      bounty_th_remain: 'Quota Left',
      bounty_th_surplus: 'Days Left',
      bounty_th_state: 'State',
      bounty_th_seen: 'Status',
      bounty_th_action: 'Action',
      bounty_empty: 'No open projects. Waiting for monitor...',
      bounty_apply: 'Apply',
      bounty_state_apply: 'Applying',
      bounty_state_doing: 'Running',
      bounty_state_pause: 'Paused',
      bounty_state_stop: 'Ended',
      bounty_closed: 'Closed',
      bounty_open: 'Open',
      bounty_th_apply_status: 'Applied',
      bounty_applied: 'Auto-applied',
      bounty_apply_failed: 'Apply failed',
      bounty_retry_apply: 'Retry',
      bounty_apply_ok: 'Applied',
      bounty_auto_apply: 'Auto apply (call platform API on new projects)',
      bounty_auto_apply_hint: 'Automatically apply to each newly detected open project with your account; failures are pushed via WeChat/email. Account must pass real-name verification.',
      bounty_fast_poll: 'Fast poll (second-level)',
      bounty_fast_poll_hint: 'Dedicated thread polls every N seconds and applies immediately. Smaller interval = faster, but sustained high-frequency requests may trigger rate limiting/ban. 2-3s recommended.',
      bounty_poll_seconds: 'Fast poll interval (sec, 1-60)',

      // ---- 360众测 (EN) ----
      zc_title: '360 Zhongce',
      zc_settings_title: '360 Zhongce Monitor',
      zc_scan_now: 'Scan now',
      zc_search_ph: 'Search projects...',
      zc_open_only: 'Open only',
      zc_new_only: 'New only',
      zc_mark_all: 'Mark all read',
      zc_th_name: 'Project',
      zc_th_reward: 'Reward (¥)',
      zc_th_surplus: 'Days Left',
      zc_th_state: 'Start time',
      zc_th_seen: 'Status',
      zc_th_apply: 'Applied',
      zc_th_action: 'Action',
      zc_empty: 'No projects. Waiting for monitor...',
      zc_open: 'Open',
      zc_closed: 'Closed',
      zc_apply: 'Apply',
      zc_applied: 'Auto-applied',
      zc_apply_failed: 'Apply failed',
      zc_retry_apply: 'Retry',
      zc_apply_ok: 'Applied',
      zc_cookie_label: '360 Zhongce Cookie (full login cookie)',
      zc_cookie_hint: 'Login zhongce.360.net, F12 → Network → any request → copy the full Cookie header value (keep semicolon-separated format).',
      zc_interval: 'Poll interval (sec, 1-60)',
      zc_auto_apply: 'Auto apply',
      zc_auto_apply_hint: 'Auto apply to new projects. Account must pass real-name verification + profile + NDA + technical assessment, otherwise platform rejects.',
      zc_fast_poll: 'Fast poll (second-level)',

      // ---- SRC 秒级 (EN) ----
      src_settings_title: 'SRC Monitor (Butian/Vulbox)',
      src_fast_poll: 'Second-level polling',
      src_fast_poll_hint: 'Poll Butian and Vulbox every N seconds and notify on new companies/programs. Default 5s; smaller = faster but may trigger rate limiting.',
      src_poll_seconds: 'Poll interval (sec, 1-60)',
      bounty_interval: 'Interval (min, 1-60)',
      bounty_token_title: 'BountyTeam',
      bounty_token_label: 'BountyTeam Token (jwtToken)',
      bounty_token_hint: 'Login bountyteam.com, run localStorage.getItem("jwtToken") in console',
      settings_bounty_title: 'BountyTeam Monitor',

      // ---- Toast ----
      toast_paused: 'Paused',
      toast_resumed: 'Resumed',
      toast_scanning: 'Scanning...',
      toast_scan_done: 'Scan done: ',
      toast_assets: ' assets, ',
      toast_new: ' new',
      toast_deleted: 'Deleted',
      toast_domain_empty: 'Please enter a domain',
      toast_added: 'Added: ',
      toast_assets_found: ' assets',
      toast_marked: 'Marked all as seen',
      toast_settings_saved: 'Settings saved',
      toast_failed: 'Failed',

      // ---- Confirm ----
      confirm_delete: 'Delete this domain and all its assets?',

      // ---- Time ----
      time_never: 'Never',

      // ---- Misc ----
      brand: 'Asset Monitoring System',
    },
  };

  let _current = localStorage.getItem('lang') || 'zh';

  function get(key) {
    return (translations[_current] && translations[_current][key]) || key;
  }

  function current() {
    return _current;
  }

  function set(lang) {
    _current = lang;
    localStorage.setItem('lang', lang);
  }

  function apply() {
    // Apply data-i18n attributes
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (key) el.textContent = get(key);
    });
    // Apply data-i18n-placeholder
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      if (key) el.setAttribute('placeholder', get(key));
    });
    // Apply data-i18n-value
    document.querySelectorAll('[data-i18n-value]').forEach(el => {
      const key = el.getAttribute('data-i18n-value');
      if (key) el.setAttribute('value', get(key));
    });
    // Update page title
    if (document.title) {
      const t = document.querySelector('title');
      if (t && t.hasAttribute('data-i18n-key')) {
        document.title = get(t.getAttribute('data-i18n-key'));
      }
    }
  }

  // Lang toggle UI
  function renderToggle() {
    const existing = document.getElementById('lang-toggle');
    if (existing) existing.remove();

    const btn = document.createElement('button');
    btn.id = 'lang-toggle';
    btn.className = 'lang-toggle-btn';
    btn.textContent = _current === 'zh' ? 'EN' : '中文';
    btn.title = _current === 'zh' ? 'Switch to English' : '切换到中文';
    btn.addEventListener('click', () => {
      const next = _current === 'zh' ? 'en' : 'zh';
      set(next);
      btn.textContent = next === 'zh' ? 'EN' : '中文';
      btn.title = next === 'zh' ? 'Switch to English' : '切换到中文';
      apply();
      window.dispatchEvent(new CustomEvent('langchange', { detail: { lang: next } }));
    });
    // Prefer nav container on dashboard, fallback to body on login
    const container = document.getElementById('lang-toggle-container') || document.body;
    container.appendChild(btn);
  }

  function init() {
    renderToggle();
    apply();
  }

  return { get, current, set, apply, init, renderToggle };
})();
