/* ================================================================
   AssetMonitor // Frontend Application (i18n-aware)
   ================================================================ */
(function() {
  'use strict';

  // ========== Token & API ==========
  const Token = {
    get: () => localStorage.getItem('jwt'),
    set: (t) => localStorage.setItem('jwt', t),
    clear: () => { localStorage.removeItem('jwt'); localStorage.removeItem('user'); },
  };

  if (!Token.get() && window.location.pathname !== '/') {
    window.location.href = '/';
    return;
  }
  if (Token.get() && window.location.pathname === '/') {
    window.location.href = '/dashboard';
    return;
  }

  // ========== API Helper ==========
  async function api(url, options = {}) {
    const token = Token.get();
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (token) headers['Authorization'] = 'Bearer ' + token;
    const resp = await fetch(url, { ...options, headers });
    if (resp.status === 401) {
      Token.clear();
      window.location.href = '/';
      throw new Error('Unauthorized');
    }
    return resp;
  }

  // ========== Toast ==========
  function toast(msg, type = 'success') {
    const container = document.getElementById('toast-container');
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(() => { el.remove(); }, 3500);
  }

  // ========== Navigation ==========
  function showSection(name) {
    document.querySelectorAll('.content-section').forEach(s => s.style.display = 'none');
    const sec = document.getElementById('section-' + name);
    if (sec) sec.style.display = '';
    document.querySelectorAll('.nav-links a[data-section]').forEach(a => a.classList.remove('active'));
    const link = document.querySelector('.nav-links a[data-section="' + name + '"]');
    if (link) link.classList.add('active');
  }

  document.querySelectorAll('.nav-links a[data-section]').forEach(a => {
    a.addEventListener('click', (e) => { e.preventDefault(); showSection(a.dataset.section); });
  });

  // ========== Logout ==========
  document.getElementById('logout-btn').addEventListener('click', (e) => {
    e.preventDefault();
    Token.clear();
    window.location.href = '/';
  });

  // ========== Stats ==========
  async function loadStats() {
    try {
      const resp = await api('/api/stats');
      const data = await resp.json();
      document.getElementById('stat-domains').textContent = data.active_domains + '/' + data.total_domains;
      document.getElementById('stat-assets').textContent = data.total_assets;
      document.getElementById('stat-new').textContent = data.new_assets;
      document.getElementById('stat-today').textContent = data.today_new;
    } catch (e) { /* skip */ }
  }

  // ========== Domains ==========
  function renderDomainRow(d) {
    const paused = d.status === 'paused';
    const actPause = I18N.get('act_pause');
    const actResume = I18N.get('act_resume');
    const actScan = I18N.get('act_scan');
    const actDel = I18N.get('act_del');
    const actEdit = I18N.get('act_edit') || 'Edit';
    const statusActive = I18N.get('status_active');
    const statusPaused = I18N.get('status_paused');

    let actions = '';
    if (paused) {
      actions = '<button class="btn-sm btn-primary resume-btn" data-id="' + d.id + '">' + actResume + '</button>';
    } else {
      actions = '<button class="btn-sm btn-warn pause-btn" data-id="' + d.id + '">' + actPause + '</button>';
    }
    actions +=
      '<button class="btn-sm btn-primary scan-btn" data-id="' + d.id + '" style="margin-left:4px;">' + actScan + '</button>' +
      '<button class="btn-sm btn-secondary edit-btn" data-id="' + d.id + '" data-int="' + d.interval_hours + '" style="margin-left:4px;">' + actEdit + '</button>' +
      '<button class="btn-sm btn-danger del-btn" data-id="' + d.id + '" style="margin-left:4px;">' + actDel + '</button>';

    return '<tr>' +
      '<td><a href="#" class="domain-link" data-id="' + d.id + '" data-domain="' + esc(d.domain) + '">' + esc(d.domain) + '</a></td>' +
      '<td><span style="color:var(--cyan-dim);font-size:0.78rem;">' + esc(d.organization || '-') + '</span></td>' +
      '<td><span class="status-badge ' + d.status + '">' + (paused ? statusPaused : statusActive) + '</span></td>' +
      '<td>' + d.asset_count + '</td>' +
      '<td><span class="status-badge new">' + d.new_count + '</span></td>' +
      '<td>' + d.interval_hours + 'h</td>' +
      '<td>' + (d.last_scan_at ? fmtTime(d.last_scan_at) : I18N.get('time_never')) + '</td>' +
      '<td>' + actions + '</td>' +
    '</tr>';
  }

  async function loadDomains() {
    try {
      const org = document.getElementById('org-filter').value;
      let url = '/api/domains?_=' + (new Date()).getTime();
      if (org) url += '&organization=' + encodeURIComponent(org);
      if (SortState['domain']) url += sortParams('domain');
      else if (SortState['asset_count']) url += sortParams('asset_count');
      else if (SortState['interval_hours']) url += sortParams('interval_hours');
      else if (SortState['last_scan_at']) url += sortParams('last_scan_at');
      else if (SortState['status']) url += sortParams('status');
      const resp = await api(url);
      if (!resp || !resp.ok) { console.error('loadDomains failed', resp); return; }
      const data = await resp.json();
      const tbody = document.querySelector('#domains-table tbody');
      const empty = '<tr><td colspan="7" style="text-align:center;color:var(--text-dim);">' + I18N.get('domain_empty') + '</td></tr>';
      tbody.innerHTML = data.map(renderDomainRow).join('') || empty;
      bindDomainActions();
      updateSortIcons('domains-table');
    } catch (e) { console.error('loadDomains error', e); }
  }

  function bindDomainActions() {
    document.querySelectorAll('.pause-btn').forEach(b => b.addEventListener('click', async () => {
      const id = b.dataset.id;
      await api('/api/domains/' + id + '/pause', { method: 'POST' });
      toast(I18N.get('toast_paused'));
      loadDomains(); loadStats();
    }));
    document.querySelectorAll('.resume-btn').forEach(b => b.addEventListener('click', async () => {
      const id = b.dataset.id;
      await api('/api/domains/' + id + '/resume', { method: 'POST' });
      toast(I18N.get('toast_resumed'));
      loadDomains(); loadStats();
    }));
    document.querySelectorAll('.scan-btn').forEach(b => b.addEventListener('click', async () => {
      const id = b.dataset.id;
      toast(I18N.get('toast_scanning'));
      const resp = await api('/api/domains/' + id + '/scan', { method: 'POST' });
      const data = await resp.json();
      toast(I18N.get('toast_scan_done') + data.assets_found + I18N.get('toast_assets') + data.new_count + I18N.get('toast_new'));
      loadDomains(); loadStats();
    }));
    document.querySelectorAll('.del-btn').forEach(b => b.addEventListener('click', async () => {
      if (!confirm(I18N.get('confirm_delete'))) return;
      const id = b.dataset.id;
      await api('/api/domains/' + id, { method: 'DELETE' });
      toast(I18N.get('toast_deleted'));
      loadDomains(); loadStats();
    }));
    document.querySelectorAll('.edit-btn').forEach(b => b.addEventListener('click', async () => {
      const id = b.dataset.id;
      const cur = parseInt(b.dataset.int) || 6;
      const val = prompt((I18N.current() === 'zh' ? '修改扫描间隔 (小时, 当前:' : 'Change scan interval (hours, current:') + cur + '):', cur);
      if (val === null) return;
      const h = parseInt(val);
      if (!h || h < 1 || h > 168) {
        toast(I18N.current() === 'zh' ? '请输入1-168之间的数字' : 'Please enter a number between 1-168', 'error');
        return;
      }
      await api('/api/domains/' + id, {
        method: 'PUT',
        body: JSON.stringify({ interval_hours: h }),
      });
      toast((I18N.current() === 'zh' ? '已更新间隔为 ' : 'Interval updated to ') + h + 'h');
      loadDomains();
    }));
    document.querySelectorAll('.domain-link').forEach(a => a.addEventListener('click', (e) => {
      e.preventDefault();
      document.getElementById('asset-search').value = '';
      document.getElementById('asset-new-only').checked = false;
      showSection('assets');
      loadAssets(1, a.dataset.id);
    }));
  }

  document.getElementById('add-domain-btn').addEventListener('click', async () => {
    const domain = document.getElementById('new-domain').value.trim();
    const org = document.getElementById('new-org').value.trim();
    const interval = parseInt(document.getElementById('new-interval').value) || 6;
    if (!domain) { toast(I18N.get('toast_domain_empty'), 'error'); return; }
    const btn = document.getElementById('add-domain-btn');
    btn.disabled = true;
    btn.textContent = '...';
    try {
      const resp = await api('/api/domains', {
        method: 'POST',
        body: JSON.stringify({ domain, organization: org, interval_hours: interval }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        toast(data.error || I18N.get('toast_failed'), 'error');
        btn.disabled = false;
        btn.textContent = I18N.get('domain_add_btn');
        return;
      }
      document.getElementById('new-domain').value = '';
      document.getElementById('new-interval').value = '6';
      // Force immediate refresh
      await loadDomains();
      await loadStats();
      toast(
        I18N.current() === 'zh'
          ? '✓ 已添加 ' + data.domain + '，发现 ' + data.asset_count + ' 个资产'
          : '✓ Added ' + data.domain + ', found ' + data.asset_count + ' assets',
        'success'
      );
    } catch(e) {
      toast(I18N.get('toast_failed'), 'error');
    }
    btn.disabled = false;
    btn.textContent = I18N.get('domain_add_btn');
  });

  // Batch import toggle
  document.getElementById('show-batch-btn').addEventListener('click', () => {
    const row = document.getElementById('batch-import-row');
    row.style.display = row.style.display === 'none' ? '' : 'none';
  });

  // Batch import execute
  document.getElementById('batch-import-btn').addEventListener('click', async () => {
    const org = document.getElementById('batch-org').value.trim();
    const text = document.getElementById('batch-domains').value.trim();
    const intv = parseInt(document.getElementById('batch-interval').value) || 6;
    if (!text) { toast(I18N.get('toast_domain_empty'), 'error'); return; }
    const btn = document.getElementById('batch-import-btn');
    btn.disabled = true; btn.textContent = '...';
    const res = document.getElementById('batch-result');
    try {
      const resp = await api('/api/domains/batch', {
        method: 'POST',
        body: JSON.stringify({ organization: org, domains: text, interval_hours: intv }),
      });
      const data = await resp.json();
      res.innerHTML = '<span style="color:var(--text);">✓ ' + data.message + '</span>'
        + (data.added && data.added.length ? '<br><span style="color:var(--text-dim);">新增: ' + data.added.join(', ') + '</span>' : '')
        + (data.skipped && data.skipped.length ? '<br><span style="color:var(--amber);">已跳过: ' + data.skipped.join(', ') + '</span>' : '');
      toast(data.message);
      document.getElementById('batch-domains').value = '';
      await loadDomains();
      await loadStats();
      loadOrgFilter();
    } catch(e) { toast(I18N.get('toast_failed'), 'error'); }
    btn.disabled = false; btn.textContent = I18N.get('domain_batch_run');
  });

  // Organization filter
  document.getElementById('org-filter').addEventListener('change', () => loadDomains());

  async function loadOrgFilter() {
    try {
      const resp = await api('/api/organizations');
      const data = await resp.json();
      const sel = document.getElementById('org-filter');
      const cur = sel.value;
      sel.innerHTML = '<option value="">全部</option>' + data.map(o =>
        '<option value="' + esc(o.name) + '">' + esc(o.name) + ' (' + o.domain_count + ')</option>'
      ).join('');
      sel.value = cur;
    } catch(e) {}
  }

  // ========== Assets ==========
  let _currentDomainId = null;

  function renderAssetRow(a) {
    return '<tr>' +
      '<td>' + esc(a.subdomain) + '</td>' +
      '<td>' + esc(a.domain || '') + '</td>' +
      '<td style="font-size:0.75rem;">' + esc(a.ip_addresses || '-') + '</td>' +
      '<td>' + esc(a.source) + '</td>' +
      '<td>' + fmtTime(a.first_seen) + '</td>' +
      '<td>' + (a.is_new
        ? '<span class="status-badge new">' + I18N.get('status_new') + '</span>'
        : '<span style="color:var(--text-dim);">' + I18N.get('status_seen') + '</span>') +
      '</td>' +
      '<td>' + (a.is_new
        ? '<button class="btn-sm btn-secondary mark-seen" data-id="' + a.id + '">✓ ' + I18N.get('status_seen') + '</button>'
        : '') +
      '</td>' +
    '</tr>';
  }

  function renderPager(total, page, perPage, fn) {
    const pages = Math.ceil(total / perPage) || 1;
    let html = '';
    html += '<button ' + (page <= 1 ? 'disabled' : '') + ' data-p="' + (page - 1) + '">' + I18N.get('pager_prev') + '</button>';
    for (let p = 1; p <= pages; p++) {
      if (p > 1 && p < page - 2 && p > 2) { html += '<span>...</span>'; p = page - 2; continue; }
      if (p < pages && p > page + 2) { html += '<span>...</span>'; p = pages - 1; continue; }
      html += '<button class="' + (p === page ? 'active' : '') + '" data-p="' + p + '">' + p + '</button>';
    }
    html += '<button ' + (page >= pages ? 'disabled' : '') + ' data-p="' + (page + 1) + '">' + I18N.get('pager_next') + '</button>';
    html += '<span>' + total + ' ' + I18N.get('pager_total') + '</span>';
    return html;
  }

  async function loadAssets(page = 1, domainId = null) {
    _currentDomainId = domainId;
    const search = document.getElementById('asset-search').value.trim();
    const newOnly = document.getElementById('asset-new-only').checked ? '1' : '0';

    let url;
    if (domainId) {
      url = '/api/domains/' + domainId + '/assets?page=' + page + '&per_page=50&new_only=' + newOnly;
      if (search) url += '&search=' + encodeURIComponent(search);
    } else {
      url = '/api/assets?page=' + page + '&per_page=50&new_only=' + newOnly;
      if (search) url += '&search=' + encodeURIComponent(search);
    }
    // Append sort params
    for (const k of ['subdomain','ip_addresses','source','first_seen']) {
      if (SortState[k]) { url += sortParams(k); break; }
    }

    const resp = await api(url);
    const data = await resp.json();
    const tbody = document.getElementById('assets-table').querySelector('tbody');
    const empty = '<tr><td colspan="7" style="text-align:center;color:var(--text-dim);">' + I18N.get('asset_empty') + '</td></tr>';
    tbody.innerHTML = data.assets.map(renderAssetRow).join('') || empty;
    updateSortIcons('assets-table');
    document.getElementById('assets-pager').innerHTML = renderPager(data.total, data.page, data.per_page, loadAssets);

    document.getElementById('assets-pager').querySelectorAll('button[data-p]').forEach(b => {
      b.addEventListener('click', () => loadAssets(parseInt(b.dataset.p), _currentDomainId));
    });
    document.querySelectorAll('.mark-seen').forEach(b => b.addEventListener('click', async () => {
      await api('/api/assets/' + b.dataset.id + '/mark-seen', { method: 'POST' });
      loadAssets(page, _currentDomainId);
      loadStats();
    }));
  }

  document.getElementById('asset-search').addEventListener('input', () => loadAssets(1, _currentDomainId));
  document.getElementById('asset-new-only').addEventListener('change', () => loadAssets(1, _currentDomainId));
  document.getElementById('mark-all-btn').addEventListener('click', async () => {
    const body = _currentDomainId ? JSON.stringify({ domain_id: _currentDomainId }) : '{}';
    await api('/api/assets/mark-all-seen', { method: 'POST', body });
    toast(I18N.get('toast_marked'));
    loadAssets(1, _currentDomainId);
    loadStats();
  });
  document.getElementById('export-csv-btn').addEventListener('click', () => {
    const newOnly = document.getElementById('asset-new-only').checked ? '1' : '0';
    window.open('/api/assets/export?format=csv&new_only=' + newOnly, '_blank');
  });
  document.getElementById('export-json-btn').addEventListener('click', async () => {
    const newOnly = document.getElementById('asset-new-only').checked ? '1' : '0';
    const resp = await api('/api/assets/export?format=json&new_only=' + newOnly);
    const data = await resp.json();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'assets.json'; a.click();
    URL.revokeObjectURL(url);
  });

  // ========== Logs ==========
  async function loadLogs(page = 1) {
    try {
      let url = '/api/scan-logs?page=' + page + '&per_page=20';
      for (const k of ['started_at','finished_at','assets_found','new_assets_found','status']) {
        if (SortState[k]) { url += sortParams(k); break; }
      }
      const resp = await api(url);
      const data = await resp.json();
      const tbody = document.getElementById('logs-table').querySelector('tbody');
      const empty = '<tr><td colspan="6" style="text-align:center;color:var(--text-dim);">' + I18N.get('log_empty') + '</td></tr>';
      tbody.innerHTML = data.logs.map(l => '<tr>' +
        '<td>' + esc(l.domain) + '</td>' +
        '<td>' + fmtTime(l.started_at) + '</td>' +
        '<td>' + (l.finished_at ? fmtTime(l.finished_at) : '...') + '</td>' +
        '<td>' + l.assets_found + '</td>' +
        '<td>' + l.new_assets_found + '</td>' +
        '<td><span class="status-badge ' + l.status + '">' + I18N.get('status_' + l.status) + '</span></td>' +
      '</tr>').join('') || empty;
      updateSortIcons('logs-table');
      document.getElementById('logs-pager').innerHTML = renderPager(data.total, data.page, data.per_page, loadLogs);
      document.getElementById('logs-pager').querySelectorAll('button[data-p]').forEach(b => {
        b.addEventListener('click', () => loadLogs(parseInt(b.dataset.p)));
      });
    } catch (e) { /* skip */ }
  }

  // ========== Settings ==========
  async function loadSettings() {
    try {
      const resp = await api('/api/auth/me');
      const u = await resp.json();
      document.getElementById('s-pushplus').value = u.pushplus_token && u.pushplus_token !== '***' ? u.pushplus_token : '';
      document.getElementById('s-email').value = u.email || '';
      document.getElementById('s-smtp-host').value = u.smtp_host || '';
      document.getElementById('s-smtp-port').value = u.smtp_port || 587;
      document.getElementById('s-smtp-user').value = u.smtp_user || '';
      document.getElementById('s-smtp-pass').value = '';
      document.getElementById('s-smtp-from').value = u.smtp_from || '';
      document.getElementById('s-notify-email').checked = u.notify_email;
      document.getElementById('s-notify-wechat').checked = u.notify_wechat;
      document.getElementById('s-src-interval').value = u.src_interval_hours || 1;
      document.getElementById('s-bounty-token').value = u.bountyteam_token && u.bountyteam_token !== '***' ? u.bountyteam_token : '';
      document.getElementById('s-bounty-interval').value = u.bountyteam_interval_minutes || 3;
      document.getElementById('s-bounty-auto-apply').checked = !!u.bountyteam_auto_apply;
      document.getElementById('s-bounty-fast-poll').checked = !!u.bountyteam_fast_poll;
      document.getElementById('s-bounty-poll-seconds').value = u.bountyteam_poll_seconds || 3;
      document.getElementById('s-zc-cookie').value = u.zc_cookie && u.zc_cookie !== '***' ? u.zc_cookie : '';
      document.getElementById('s-zc-interval').value = u.zc_interval_seconds || 3;
      document.getElementById('s-zc-auto-apply').checked = !!u.zc_auto_apply;
      document.getElementById('s-zc-fast-poll').checked = !!u.zc_fast_poll;
      document.getElementById('s-src-fast-poll').checked = !!u.src_fast_poll;
      document.getElementById('s-src-poll-seconds').value = u.src_poll_seconds || 5;
      // Load current git remote
      try {
        const rr = await api('/api/update/remote');
        const rd = await rr.json();
        document.getElementById('s-update-repo').value = rd.remote_url || '';
      } catch (e) { /* skip */ }
    } catch (e) { /* skip */ }
  }

  // ========== Online Update ==========
  const updStatus = () => document.getElementById('update-status');
  const updApplyBtn = () => document.getElementById('update-apply-btn');

  document.getElementById('update-save-repo-btn').addEventListener('click', async () => {
    const url = document.getElementById('s-update-repo').value.trim();
    if (!url) { updStatus().textContent = I18N.get('update_no_remote'); return; }
    const resp = await api('/api/update/remote', {
      method: 'PUT', body: JSON.stringify({ remote_url: url }),
    });
    updStatus().textContent = resp.ok ? I18N.get('update_repo_saved')
      : I18N.get('update_failed') + 'save failed';
  });

  document.getElementById('update-check-btn').addEventListener('click', async () => {
    updStatus().textContent = I18N.get('update_checking');
    updApplyBtn().style.display = 'none';
    try {
      const resp = await api('/api/update/check', { method: 'POST' });
      const d = await resp.json();
      if (d.error === 'no_remote') {
        updStatus().textContent = I18N.get('update_no_remote');
        return;
      }
      if (d.error) {
        updStatus().textContent = I18N.get('update_failed') + (d.detail || d.error);
        return;
      }
      let txt = `${I18N.get('update_branch')}: ${d.branch}\n` +
                `${I18N.get('update_current')}: ${d.current}  ${I18N.get('update_remote')}: ${d.remote}`;
      if (d.has_update) {
        txt += `\n${I18N.get('update_found')}${d.behind}${I18N.get('update_commits')}\n`;
        (d.commits || []).forEach(c => {
          txt += `\n[${c.hash}] ${c.subject} — ${c.author} (${c.date})`;
        });
        updApplyBtn().style.display = '';
      } else {
        txt += `\n${I18N.get('update_latest')}`;
      }
      updStatus().textContent = txt;
    } catch (e) {
      updStatus().textContent = I18N.get('update_failed') + e.message;
    }
  });

  document.getElementById('update-apply-btn').addEventListener('click', async () => {
    if (!confirm(I18N.get('update_confirm'))) return;
    updStatus().textContent = I18N.get('update_applying');
    try {
      const resp = await api('/api/update/apply', { method: 'POST' });
      const d = await resp.json();
      if (resp.ok) {
        updStatus().textContent = I18N.get('update_done');
        setTimeout(() => location.reload(), 6000);
      } else {
        updStatus().textContent = I18N.get('update_failed') + (d.message || '');
      }
    } catch (e) {
      updStatus().textContent = I18N.get('update_failed') + e.message;
    }
  });

  document.getElementById('save-settings-btn').addEventListener('click', async () => {
    const body = {
      pushplus_token: document.getElementById('s-pushplus').value.trim(),
      email: document.getElementById('s-email').value.trim(),
      smtp_host: document.getElementById('s-smtp-host').value.trim(),
      smtp_port: parseInt(document.getElementById('s-smtp-port').value) || 587,
      smtp_user: document.getElementById('s-smtp-user').value.trim(),
      smtp_pass: document.getElementById('s-smtp-pass').value,
      smtp_from: document.getElementById('s-smtp-from').value.trim(),
      notify_email: document.getElementById('s-notify-email').checked,
      notify_wechat: document.getElementById('s-notify-wechat').checked,
      src_interval_hours: parseInt(document.getElementById('s-src-interval').value) || 1,
      bountyteam_interval_minutes: parseInt(document.getElementById('s-bounty-interval').value) || 3,
      bountyteam_auto_apply: document.getElementById('s-bounty-auto-apply').checked,
      bountyteam_fast_poll: document.getElementById('s-bounty-fast-poll').checked,
      bountyteam_poll_seconds: parseInt(document.getElementById('s-bounty-poll-seconds').value) || 3,
      zc_interval_seconds: parseInt(document.getElementById('s-zc-interval').value) || 3,
      zc_auto_apply: document.getElementById('s-zc-auto-apply').checked,
      zc_fast_poll: document.getElementById('s-zc-fast-poll').checked,
      src_fast_poll: document.getElementById('s-src-fast-poll').checked,
      src_poll_seconds: parseInt(document.getElementById('s-src-poll-seconds').value) || 5,
    };
    // token 仅在用户实际输入了内容时提交 (避免把 *** 覆盖回库)
    const btToken = document.getElementById('s-bounty-token').value.trim();
    if (btToken && btToken !== '***') {
      body.bountyteam_token = btToken;
    }
    // 360 cookie 同样: 仅在输入了非脱敏值时提交
    const zcCookie = document.getElementById('s-zc-cookie').value.trim();
    if (zcCookie && zcCookie !== '***') {
      body.zc_cookie = zcCookie;
    }
    const resp = await api('/api/settings', { method: 'PUT', body: JSON.stringify(body) });
    const msgEl = document.getElementById('settings-msg');
    if (resp.ok) {
      msgEl.textContent = I18N.get('settings_saved');
      msgEl.style.color = 'var(--text)';
      toast(I18N.get('toast_settings_saved'));
    } else {
      msgEl.textContent = I18N.get('settings_failed');
      msgEl.style.color = 'var(--danger)';
    }
  });

  // ========== Section switch hooks ==========
  document.querySelector('.nav-links a[data-section="assets"]').addEventListener('click', () => {
    document.getElementById('asset-search').value = '';
    document.getElementById('asset-new-only').checked = false;
    _currentDomainId = null;
    loadAssets(1);
  });
  document.querySelector('.nav-links a[data-section="logs"]').addEventListener('click', () => loadLogs(1));
  document.querySelector('.nav-links a[data-section="settings"]').addEventListener('click', loadSettings);

  // ========== Helpers ==========
  function esc(s) {
    if (!s) return '';
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }
  function fmtTime(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    const pad = (n) => String(n).padStart(2, '0');
    return (
      d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
      ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes())
    );
  }

  // ========== Sort ==========
  const SortState = {};
  function sortIcon(key) {
    const st = SortState[key];
    if (!st) return ' <span style="color:#444;">▽</span>';
    return st === 'asc' ? ' <span style="color:var(--cyan);">▲</span>' : ' <span style="color:var(--cyan);">▼</span>';
  }
  function sortKey(key) {
    SortState[key] = SortState[key] === 'desc' ? 'asc' : 'desc';
  }
  function sortParams(key) {
    const asc = SortState[key] === 'asc';
    return '&sort_by=' + key + '&sort_asc=' + (asc ? '1' : '0');
  }
  function sortableTH(colKey, labelKey) {
    return '<th data-sort="' + colKey + '" style="cursor:pointer;user-select:none;">' + I18N.get(labelKey) + sortIcon(colKey) + '</th>';
  }
  // Click delegation: set up once on parent, call callback(colKey) on click
  function bindSortClicks(containerId, callback) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.addEventListener('click', function(e) {
      const th = e.target.closest('th[data-sort]');
      if (!th) return;
      e.preventDefault();
      sortKey(th.dataset.sort);
      callback();
    });
  }
  // Refresh sort icons in a table
  function updateSortIcons(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;
    table.querySelectorAll('th[data-sort]').forEach(th => {
      const key = th.dataset.sort;
      // Remove existing sort icon
      const existing = th.querySelector('.sort-icon');
      if (existing) existing.remove();
      const icon = document.createElement('span');
      icon.className = 'sort-icon';
      icon.style.cssText = 'margin-left:3px;font-size:0.65rem;';
      const st = SortState[key];
      icon.textContent = st === 'asc' ? '▲' : st === 'desc' ? '▼' : '▽';
      icon.style.color = st ? 'var(--cyan)' : '#444';
      th.appendChild(icon);
    });
  }

  // ---- Sort click bindings (set up once) ----
  bindSortClicks('domains-table', loadDomains);
  bindSortClicks('assets-table', () => loadAssets(1, _currentDomainId));
  bindSortClicks('src-table', () => loadSrcPrograms(1));
  bindSortClicks('logs-table', () => loadLogs(1));

  // ========== SRC Platform Monitor ==========
  let _srcPage = 1;

  function renderSrcRow(p) {
    const platformLabel = p.platform === 'butian' ? '补天' : '漏洞盒子';
    const tabLabel = p.tab === 'corps' ? '企业SRC' : p.tab === 'com' ? '专属SRC' : p.tab === 'pub' ? '公益SRC' : '企业SRC';
    const reward = p.reward_min || p.reward_max ? (p.reward_min + ' ~ ' + p.reward_max + ' 元') : '-';
    return '<tr>' +
      '<td><span style="color:var(--cyan);">' + platformLabel + '</span> <span style="color:var(--text-dim);font-size:0.7rem;">' + tabLabel + '</span></td>' +
      '<td>' + esc(p.company_name) + (p.recommend ? ' <span style="color:var(--amber);font-size:0.65rem;">★荐</span>' : '') + '</td>' +
      '<td>' + reward + '</td>' +
      '<td style="font-size:0.75rem;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + esc(p.description) + '">' + esc(p.description) + '</td>' +
      '<td style="font-size:0.75rem;">' + (p.change_time ? fmtTime(p.change_time) : '-') + '</td>' +
      '<td>' + (p.is_new
        ? '<span class="status-badge new">' + I18N.get('status_new') + '</span>'
        : '<span style="color:var(--text-dim);">' + I18N.get('status_seen') + '</span>') + '</td>' +
    '</tr>';
  }

  async function loadSrcPrograms(page = 1) {
    _srcPage = page;
    const platform = document.getElementById('src-platform-filter').value;
    const onlyNew = document.getElementById('src-new-only').checked ? '1' : '0';
    const search = document.getElementById('src-search').value.trim();

    let url = '/api/src-programs?page=' + page + '&per_page=50&new_only=' + onlyNew;
    if (platform) url += '&platform=' + platform;
    if (search) url += '&search=' + encodeURIComponent(search);
    for (const k of ['platform','company_name','reward_max','change_time','first_seen']) {
      if (SortState[k]) { url += sortParams(k); break; }
    }

    const resp = await api(url);
    const data = await resp.json();
    const tbody = document.getElementById('src-table').querySelector('tbody');
    const empty = '<tr><td colspan="6" style="text-align:center;color:var(--text-dim);">' + (I18N.get('src_empty') || '暂无数据，点击"立即扫描"') + '</td></tr>';
    tbody.innerHTML = data.programs.map(renderSrcRow).join('') || empty;
    updateSortIcons('src-table');
    document.getElementById('src-pager').innerHTML = renderPager(data.total, data.page, data.per_page, loadSrcPrograms);
    document.getElementById('src-pager').querySelectorAll('button[data-p]').forEach(b => {
      b.addEventListener('click', () => loadSrcPrograms(parseInt(b.dataset.p)));
    });

    // Mini stats
    const statsResp = await api('/api/src-stats');
    const stats = await statsResp.json();
    document.getElementById('src-stats-mini').innerHTML =
      '<span style="font-size:0.78rem;color:var(--cyan);">补天: <b>' + stats.butian + '</b></span>' +
      '<span style="font-size:0.78rem;color:var(--purple);">漏洞盒子: <b>' + stats.vulbox + '</b></span>' +
      '<span style="font-size:0.78rem;color:var(--amber);">总计: <b>' + stats.total + '</b></span>' +
      '<span style="font-size:0.78rem;color:var(--pink);">新增: <b>' + stats.new + '</b></span>';
  }

  document.getElementById('src-scan-btn').addEventListener('click', async () => {
    toast(I18N.get('toast_scanning'));
    const resp = await api('/api/src-programs/scan', { method: 'POST' });
    const data = await resp.json();
    toast('SRC ' + I18N.get('toast_scan_done') + data.total + I18N.get('toast_assets') + data.new_count + I18N.get('toast_new'));
    loadSrcPrograms(1);
    loadStats();
  });
  document.getElementById('src-search').addEventListener('input', () => loadSrcPrograms(1));
  document.getElementById('src-new-only').addEventListener('change', () => loadSrcPrograms(1));
  document.getElementById('src-platform-filter').addEventListener('change', () => loadSrcPrograms(1));
  document.getElementById('src-mark-all-btn').addEventListener('click', async () => {
    await api('/api/src-programs/mark-all-seen', { method: 'POST' });
    toast(I18N.get('toast_marked'));
    loadSrcPrograms(1);
  });
  document.getElementById('src-export-csv-btn').addEventListener('click', () => {
    const no = document.getElementById('src-new-only').checked ? '1' : '0';
    window.open('/api/src-programs/export?format=csv&new_only=' + no, '_blank');
  });

  document.querySelector('.nav-links a[data-section="src"]').addEventListener('click', () => {
    loadSrcPrograms(1);
  });

  // ========== BountyTeam (雷神众测) ==========
  let _bountyPage = 1;

  function bountyStateLabel(s) {
    const m = {
      apply: I18N.get('bounty_state_apply'),
      doing: I18N.get('bounty_state_doing'),
      pause: I18N.get('bounty_state_pause'),
      stop: I18N.get('bounty_state_stop'),
    };
    return m[s] || s || '-';
  }

  function renderBountyRow(p) {
    const reward = (p.reward_max || p.reward_min)
      ? (p.reward_min + ' ~ ' + p.reward_max)
      : '-';
    const rem = p.remainder_num || '-';
    const open = p.is_open;
    const stateBadge = open
      ? '<span class="status-badge active" style="color:var(--cyan);">' + bountyStateLabel(p.states) + '</span>'
      : '<span class="status-badge paused">' + I18N.get('bounty_closed') + '</span>';
    const newBadge = p.is_new
      ? ' <span class="status-badge new">' + I18N.get('status_new') + '</span>'
      : '';
    let applyBadge = '';
    if (p.apply_status === 'applied') {
      applyBadge = '<span class="status-badge active">✅ ' + I18N.get('bounty_applied') + '</span>';
    } else if (p.apply_status === 'failed') {
      applyBadge = '<span class="status-badge paused" title="' + esc(p.apply_err || '') + '">❌ ' + I18N.get('bounty_apply_failed') + '</span>';
    }
    const applyBtn = open && p.detail_url
      ? '<a class="btn-sm btn-primary" href="' + esc(p.detail_url) + '" target="_blank" rel="noopener" style="text-decoration:none;">' + I18N.get('bounty_apply') + '</a>'
      : '';
    const retryBtn = (p.apply_status === 'failed' && open)
      ? ' <button class="btn-sm btn-secondary" onclick="retryBountyApply(' + p.project_id + ')">' + I18N.get('bounty_retry_apply') + '</button>'
      : '';
    return '<tr>' +
      '<td>' + esc(p.name) + newBadge + '</td>' +
      '<td>' + reward + '</td>' +
      '<td><b style="color:' + (open ? 'var(--amber)' : 'var(--text-dim)') + ';">' + esc(rem) + '</b></td>' +
      '<td>' + (p.surplus != null ? p.surplus + '天' : '-') + '</td>' +
      '<td style="font-size:0.75rem;">' + (p.startime ? fmtTime(p.startime) : '-') + '</td>' +
      '<td>' + stateBadge + '</td>' +
      '<td>' + applyBadge + '</td>' +
      '<td>' + applyBtn + retryBtn + '</td>' +
    '</tr>';
  }

  window.retryBountyApply = async function(pid) {
    try {
      const resp = await api('/api/bounty/projects/' + pid + '/apply', { method: 'POST' });
      const data = await resp.json();
      alert(data.ok ? (I18N.get('bounty_apply_ok') + ': ' + (data.message || '')) : (I18N.get('bounty_apply_failed') + ': ' + (data.message || '')));
      loadBountyProjects(_bountyPage);
    } catch (e) {
      alert(I18N.get('bounty_apply_failed') + ': ' + e.message);
    }
  };

  async function loadBountyProjects(page = 1) {
    _bountyPage = page;
    const openOnly = document.getElementById('bounty-open-only').checked ? '1' : '0';
    const newOnly = document.getElementById('bounty-new-only').checked ? '1' : '0';
    const search = document.getElementById('bounty-search').value.trim();

    let url = '/api/bounty/projects?page=' + page + '&per_page=50&open_only=' + openOnly + '&new_only=' + newOnly;
    if (search) url += '&search=' + encodeURIComponent(search);
    for (const k of ['name','reward_max','surplus','startime','first_seen']) {
      if (SortState[k]) { url += sortParams(k); break; }
    }

    const resp = await api(url);
    const data = await resp.json();
    const tbody = document.getElementById('bounty-table').querySelector('tbody');
    const empty = '<tr><td colspan="8" style="text-align:center;color:var(--text-dim);">' + I18N.get('bounty_empty') + '</td></tr>';
    tbody.innerHTML = (data.projects || []).map(renderBountyRow).join('') || empty;
    updateSortIcons('bounty-table');
    document.getElementById('bounty-pager').innerHTML = renderPager(data.total, data.page, data.per_page, loadBountyProjects);
    document.getElementById('bounty-pager').querySelectorAll('button[data-p]').forEach(b => {
      b.addEventListener('click', () => loadBountyProjects(parseInt(b.dataset.p)));
    });

    // mini stats
    try {
      const sr = await api('/api/bounty/stats');
      const sd = await sr.json();
      // token 健康徽章
      let badge;
      if (!sd.token_configured) {
        badge = '<span class="status-badge paused" style="color:var(--text-dim);">未配置Token</span>';
      } else if (sd.token_status === 'ok') {
        badge = '<span class="status-badge active" style="color:var(--cyan);">Token有效</span>';
      } else if (sd.token_status === 'expired') {
        badge = '<span class="status-badge paused" style="color:var(--danger);">Token已过期</span>';
      } else {
        badge = '<span class="status-badge paused" style="color:var(--text-dim);">Token状态未知</span>';
      }
      document.getElementById('bounty-stats-mini').innerHTML =
        badge +
        (sd.fast_poll
          ? '<span class="status-badge ' + (sd.fast_poll_running ? 'active' : 'paused') + '" style="' + (sd.fast_poll_running ? 'color:var(--amber);' : 'color:var(--danger);') + '">⚡极速 ' + (sd.fast_poll_running ? (sd.poll_seconds + 's' + (sd.last_latency_ms ? ' · 延迟' + sd.last_latency_ms + 'ms' : '')) : '未运行') + '</span>'
          : '') +
        '<span style="font-size:0.78rem;color:var(--cyan);">' + I18N.get('bounty_open') + ': <b>' + sd.open + '</b></span>' +
        '<span style="font-size:0.78rem;color:var(--amber);">' + I18N.get('status_new') + ': <b>' + sd.new + '</b></span>' +
        '<span style="font-size:0.78rem;color:var(--text-dim);">' + I18N.get('pager_total') + ': <b>' + sd.total + '</b></span>';
    } catch(e) {}
  }

  document.getElementById('bounty-scan-btn').addEventListener('click', async () => {
    toast(I18N.get('toast_scanning'));
    try {
      const resp = await api('/api/bounty/scan', { method: 'POST' });
      const data = await resp.json();
      if (!resp.ok) { toast(data.error || I18N.get('toast_failed'), 'error'); return; }
      toast('BountyTeam ' + I18N.get('toast_scan_done') + data.total + ' / +' + data.new_count + I18N.get('toast_new'));
      loadBountyProjects(1);
    } catch(e) { toast(I18N.get('toast_failed'), 'error'); }
  });
  document.getElementById('bounty-search').addEventListener('input', () => loadBountyProjects(1));
  document.getElementById('bounty-open-only').addEventListener('change', () => loadBountyProjects(1));
  document.getElementById('bounty-new-only').addEventListener('change', () => loadBountyProjects(1));
  document.getElementById('bounty-mark-all-btn').addEventListener('click', async () => {
    await api('/api/bounty/projects/mark-all-seen', { method: 'POST' });
    toast(I18N.get('toast_marked'));
    loadBountyProjects(1);
  });
  document.querySelector('.nav-links a[data-section="bounty"]').addEventListener('click', () => {
    loadBountyProjects(1);
  });
  bindSortClicks('bounty-table', () => loadBountyProjects(1));

  // ========== Lang change ==========
  window.addEventListener('langchange', () => {
    loadDomains();
    if (_currentDomainId !== null || document.getElementById('section-assets').style.display !== 'none') {
      loadAssets(1, _currentDomainId);
    }
    loadLogs(1);
    if (document.getElementById('section-src').style.display !== 'none') loadSrcPrograms(_srcPage);
    if (document.getElementById('section-bounty').style.display !== 'none') loadBountyProjects(_bountyPage);
    document.querySelectorAll('.stat-label').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (key) el.textContent = I18N.get(key);
    });
    const msgEl = document.getElementById('settings-msg');
    if (msgEl && (msgEl.textContent.includes('设置') || msgEl.textContent.includes('Settings'))) {
      msgEl.textContent = msgEl.style.color === 'var(--danger)' ? I18N.get('settings_failed') : I18N.get('settings_saved');
    }
  });

  // ========== Init ==========
  I18N.init();
  loadStats();
  loadDomains();
  loadOrgFilter();
  // Refresh SRC stat
  setInterval(async () => {
    loadStats();
    if (_currentDomainId) loadAssets(1, _currentDomainId);
    try {
      const sr = await api('/api/src-stats');
      const sd = await sr.json();
      document.getElementById('stat-src-new').textContent = sd.new;
    } catch(e){}
  }, 30000);
  // Initial SRC stat
  (async () => {
    try {
      const sr = await api('/api/src-stats');
      const sd = await sr.json();
      document.getElementById('stat-src-new').textContent = sd.new;
    } catch(e){}
  })();

  // ========== 360众测 (zhongce.360.net) ==========
  let _zcPage = 1;

  function renderZcRow(p) {
    const reward = (p.reward_max || p.reward_min)
      ? (p.reward_min + ' ~ ' + p.reward_max)
      : '-';
    const open = p.is_open;
    const stateBadge = open
      ? '<span class="status-badge active" style="color:var(--cyan);">' + (p.states || I18N.get('zc_open')) + '</span>'
      : '<span class="status-badge paused">' + I18N.get('zc_closed') + '</span>';
    const newBadge = p.is_new
      ? ' <span class="status-badge new">' + I18N.get('status_new') + '</span>'
      : '';
    let applyBadge = '';
    if (p.apply_status === 'applied') {
      applyBadge = '<span class="status-badge active">✅ ' + I18N.get('zc_applied') + '</span>';
    } else if (p.apply_status === 'failed') {
      applyBadge = '<span class="status-badge paused" title="' + esc(p.apply_err || '') + '">❌ ' + I18N.get('zc_apply_failed') + '</span>';
    }
    const applyBtn = open && p.detail_url
      ? '<a class="btn-sm btn-primary" href="' + esc(p.detail_url) + '" target="_blank" rel="noopener" style="text-decoration:none;">' + I18N.get('zc_apply') + '</a>'
      : '';
    const retryBtn = (p.apply_status === 'failed' && open)
      ? ' <button class="btn-sm btn-secondary" onclick="retryZcApply(' + p.project_id + ')">' + I18N.get('zc_retry_apply') + '</button>'
      : '';
    return '<tr>' +
      '<td>' + esc(p.name) + newBadge + '</td>' +
      '<td>' + reward + '</td>' +
      '<td>' + (p.surplus != null ? p.surplus + '天' : '-') + '</td>' +
      '<td style="font-size:0.75rem;">' + (p.startime ? fmtTime(p.startime) : '-') + '</td>' +
      '<td>' + stateBadge + '</td>' +
      '<td>' + applyBadge + '</td>' +
      '<td>' + applyBtn + retryBtn + '</td>' +
    '</tr>';
  }

  window.retryZcApply = async function(pid) {
    try {
      const resp = await api('/api/zc/projects/' + pid + '/apply', { method: 'POST' });
      const data = await resp.json();
      alert(data.ok ? (I18N.get('zc_apply_ok') + ': ' + (data.message || '')) : (I18N.get('zc_apply_failed') + ': ' + (data.message || '')));
      loadZcProjects(_zcPage);
    } catch (e) {
      alert(I18N.get('zc_apply_failed') + ': ' + e.message);
    }
  };

  async function loadZcProjects(page = 1) {
    _zcPage = page;
    const openOnly = document.getElementById('zc-open-only').checked ? '1' : '0';
    const newOnly = document.getElementById('zc-new-only').checked ? '1' : '0';
    const search = document.getElementById('zc-search').value.trim();
    let url = '/api/zc/projects?page=' + page + '&per_page=50&open_only=' + openOnly + '&new_only=' + newOnly;
    if (search) url += '&search=' + encodeURIComponent(search);
    for (const k of ['name','reward_max','surplus','startime','first_seen']) {
      if (SortState[k]) { url += sortParams(k); break; }
    }
    const resp = await api(url);
    const data = await resp.json();
    const tbody = document.getElementById('zc-table').querySelector('tbody');
    const empty = '<tr><td colspan="7" style="text-align:center;color:var(--text-dim);">' + I18N.get('zc_empty') + '</td></tr>';
    tbody.innerHTML = (data.projects || []).map(renderZcRow).join('') || empty;
    updateSortIcons('zc-table');
    document.getElementById('zc-pager').innerHTML = renderPager(data.total, data.page, data.per_page, loadZcProjects);
    document.getElementById('zc-pager').querySelectorAll('button[data-p]').forEach(b => {
      b.addEventListener('click', () => loadZcProjects(parseInt(b.dataset.p)));
    });
    // mini stats
    try {
      const sr = await api('/api/zc/stats');
      const sd = await sr.json();
      let badge;
      if (!sd.cookie_configured) {
        badge = '<span class="status-badge paused" style="color:var(--text-dim);">未配置Cookie</span>';
      } else if (sd.cookie_status === 'ok') {
        badge = '<span class="status-badge active" style="color:var(--cyan);">Cookie有效</span>';
      } else if (sd.cookie_status === 'expired') {
        badge = '<span class="status-badge paused" style="color:var(--danger);">Cookie已过期</span>';
      } else {
        badge = '<span class="status-badge paused" style="color:var(--text-dim);">Cookie状态未知</span>';
      }
      document.getElementById('zc-stats-mini').innerHTML =
        badge +
        (sd.fast_poll
          ? '<span class="status-badge ' + (sd.fast_poll_running ? 'active' : 'paused') + '" style="' + (sd.fast_poll_running ? 'color:var(--amber);' : 'color:var(--danger);') + '">⚡极速 ' + (sd.fast_poll_running ? (sd.poll_seconds + 's') : '未运行') + '</span>'
          : '') +
        '<span style="font-size:0.78rem;color:var(--cyan);">' + I18N.get('zc_open') + ': <b>' + sd.open + '</b></span>' +
        '<span style="font-size:0.78rem;color:var(--amber);">' + I18N.get('status_new') + ': <b>' + sd.new + '</b></span>' +
        '<span style="font-size:0.78rem;color:var(--text-dim);">' + I18N.get('pager_total') + ': <b>' + sd.total + '</b></span>';
    } catch(e) {}
  }

  document.getElementById('zc-scan-btn').addEventListener('click', async () => {
    toast(I18N.get('toast_scanning'));
    try {
      const resp = await api('/api/zc/scan', { method: 'POST' });
      const data = await resp.json();
      if (!resp.ok) { toast(data.error || I18N.get('toast_failed'), 'error'); return; }
      toast('360众测 ' + I18N.get('toast_scan_done') + data.total + ' / +' + data.new_count + I18N.get('toast_new'));
      loadZcProjects(1);
    } catch(e) { toast(I18N.get('toast_failed'), 'error'); }
  });
  document.getElementById('zc-search').addEventListener('input', () => loadZcProjects(1));
  document.getElementById('zc-open-only').addEventListener('change', () => loadZcProjects(1));
  document.getElementById('zc-new-only').addEventListener('change', () => loadZcProjects(1));
  document.getElementById('zc-mark-all-btn').addEventListener('click', async () => {
    await api('/api/zc/projects/mark-all-seen', { method: 'POST' });
    loadZcProjects(1);
  });
  bindSortClicks('zc-table', () => loadZcProjects(1));
  document.querySelector('.nav-links a[data-section="zc"]').addEventListener('click', () => {
    loadZcProjects(1);
  });
})();
