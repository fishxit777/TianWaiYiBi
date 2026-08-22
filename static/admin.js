(() => {
  const root = document.querySelector('#admin-root');
  if (!root) return;
  const csrf = document.querySelector('meta[name="admin-csrf"]')?.content || '';
  const status = document.querySelector('#admin-status');
  const editor = document.querySelector('#idea-editor');
  const editorForm = document.querySelector('#idea-editor-form');
  let dashboard = null;

  const clear = (node) => { while (node.firstChild) node.removeChild(node.firstChild); };
  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  };
  const money = (value) => `NT$${Number(value || 0).toLocaleString('zh-TW')}`;
  const dateText = (value) => value ? String(value).replace('T', ' ').replace('+00:00', ' UTC') : '—';

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body) headers.set('Content-Type', 'application/json');
    if ((options.method || 'GET') !== 'GET') headers.set('X-CSRF-Token', csrf);
    const response = await fetch(path, {...options, headers});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `請求失敗 (${response.status})`);
    return data;
  }

  function renderMetrics(metrics) {
    const target = document.querySelector('#metric-grid');
    clear(target);
    [
      ['累計營收', money(metrics.revenue)],
      ['付費訂單', metrics.paid_orders],
      ['待付訂單', metrics.pending_orders],
      ['有效瀏覽', metrics.views],
      ['瀏覽轉換', `${metrics.conversion}%`]
    ].forEach(([label, value]) => {
      const card = node('article', 'metric-card');
      card.append(node('span', '', label), node('strong', '', value));
      target.appendChild(card);
    });
  }

  function renderRevenue(rows) {
    const target = document.querySelector('#revenue-chart');
    clear(target);
    const indexed = new Map(rows.map((item) => [item.day, Number(item.revenue || 0)]));
    const today = new Date();
    const series = [];
    for (let offset = 6; offset >= 0; offset -= 1) {
      const day = new Date(today);
      day.setDate(today.getDate() - offset);
      const key = day.toISOString().slice(0, 10);
      series.push({key, amount: indexed.get(key) || 0});
    }
    const max = Math.max(...series.map((item) => item.amount), 1);
    series.forEach((item) => {
      const wrapper = node('div', 'revenue-day');
      const progress = node('progress');
      progress.max = max;
      progress.value = item.amount;
      progress.setAttribute('aria-label', `${item.key} 營收 ${item.amount}`);
      wrapper.append(progress, node('strong', '', money(item.amount)), node('span', '', item.key.slice(5)));
      target.appendChild(wrapper);
    });
  }

  function renderTrafficSources(rows) {
    const target = document.querySelector('#traffic-sources');
    clear(target);
    const total = Math.max(rows.reduce((sum, item) => sum + Number(item.count || 0), 0), 1);
    if (!rows.length) {
      target.appendChild(node('div', 'event-empty', '尚無流量資料'));
      return;
    }
    rows.forEach((item) => {
      const row = node('div', 'traffic-source-row');
      const label = node('span', '', item.source || 'unknown');
      const track = node('div', 'traffic-track');
      const bar = node('i');
      bar.style.width = `${Math.max(4, (Number(item.count || 0) / total) * 100)}%`;
      track.appendChild(bar);
      row.append(label, track, node('strong', '', item.count));
      target.appendChild(row);
    });
  }

  function renderIntegrations(config) {
    const target = document.querySelector('#integration-grid');
    clear(target);
    [
      ['本機運行模式', '已啟用', true, '資料與測試留在本機'],
      ['公開 HTTPS', config.public_https ? '已就緒' : '待設定', config.public_https, config.base_url],
      ['LINE 正式頻道', config.line_channel ? '憑證已設定' : '待設定', config.line_channel, `已接收 ${config.line_events} 筆事件`],
      ['正式金流', config.payment_provider === 'mock' ? '模擬模式' : config.payment_provider, config.payment_provider !== 'mock', '目前不會實際扣款'],
      ['Email 交付', config.email_delivery ? '已啟用' : '待串接', config.email_delivery, '目前以專屬網址交付']
    ].forEach(([label, value, ready, detail]) => {
      const card = node('article', `integration-card ${ready ? 'ready' : 'pending'}`);
      card.append(node('span', '', label), node('strong', '', value), node('small', '', detail));
      target.appendChild(card);
    });
  }

  function setEditorValue(id, value) {
    const input = document.querySelector(id);
    if (input) input.value = value ?? '';
  }

  function openIdeaEditor(idea) {
    setEditorValue('#idea-id', idea.id);
    setEditorValue('#idea-title', idea.title);
    setEditorValue('#idea-role', idea.role);
    setEditorValue('#idea-seal', idea.seal);
    setEditorValue('#idea-accent', idea.accent);
    setEditorValue('#idea-sort-order', idea.sort_order);
    setEditorValue('#idea-price-override', idea.price_override);
    setEditorValue('#idea-discipline', idea.discipline);
    setEditorValue('#idea-summary', idea.summary);
    setEditorValue('#idea-teaser', idea.teaser);
    setEditorValue('#idea-paid-content', idea.paid_content);
    setEditorValue('#idea-deliverables', idea.deliverables);
    setEditorValue('#idea-tags', idea.tags);
    document.querySelector('#idea-editor-slug').textContent = `/${idea.slug}`;
    document.querySelector('#idea-editor-status').textContent = '';
    editor.showModal();
    document.querySelector('#idea-title').focus();
  }

  function renderIdeas(ideas) {
    const target = document.querySelector('#idea-admin-list');
    clear(target);
    ideas.forEach((idea) => {
      const row = node('div', 'idea-admin-row');
      const copy = node('div');
      copy.append(node('strong', '', idea.title), node('small', '', idea.role));
      const toggle = node('button', idea.published ? 'on' : '', idea.published ? '已上架' : '已隱藏');
      toggle.type = 'button';
      toggle.addEventListener('click', async () => {
        try {
          await api(`/admin/api/ideas/${idea.id}/publish`, {method: 'POST', body: JSON.stringify({published: !idea.published})});
          await loadDashboard('仙策上架狀態已更新。');
        } catch (error) { showError(error); }
      });
      const edit = node('button', 'edit-idea', '編輯內容');
      edit.type = 'button';
      edit.addEventListener('click', () => openIdeaEditor(idea));
      const actions = node('div', 'idea-admin-actions');
      actions.append(edit, toggle);
      row.append(node('span', '', idea.seal), copy, node('strong', '', money(idea.price)), actions);
      target.appendChild(row);
    });
  }

  function renderOrders(orders) {
    const target = document.querySelector('#orders-table');
    clear(target);
    if (!orders.length) {
      const row = node('tr');
      const cell = node('td', '', '尚無訂單');
      cell.colSpan = 6;
      row.appendChild(cell);
      target.appendChild(row);
      return;
    }
    orders.forEach((order) => {
      const row = node('tr');
      const customer = node('td');
      customer.append(node('strong', '', order.customer_name), document.createElement('br'), node('small', '', order.customer_email));
      row.append(
        node('td', '', order.order_no), node('td', '', `${order.role}｜${order.title}`), customer,
        node('td', '', money(order.amount)), node('td', `status-pill ${order.status}`, order.status),
        node('td', '', dateText(order.created_at))
      );
      target.appendChild(row);
    });
  }

  function eventItem(item, audit = false) {
    const row = node('div', `event-item severity-${item.severity || 'info'}`);
    row.append(
      node('strong', '', audit ? item.action : item.event_type),
      node('span', '', audit ? `${item.target}・${item.detail}` : `${item.ip}・${item.action_taken}・${item.path}`),
      node('time', '', dateText(item.created_at))
    );
    return row;
  }

  function renderEvents(events, selector, audit = false) {
    const target = document.querySelector(selector);
    clear(target);
    if (!events.length) {
      target.appendChild(node('div', 'event-empty', '目前沒有紀錄'));
      return;
    }
    events.forEach((item) => target.appendChild(eventItem(item, audit)));
  }

  function renderBlocks(blocks) {
    const target = document.querySelector('#blocked-ips');
    clear(target);
    if (!blocks.length) {
      target.appendChild(node('div', 'event-empty', '目前沒有封鎖 IP'));
      return;
    }
    blocks.forEach((block) => {
      const row = node('div', 'event-item block-item');
      const copy = node('div');
      copy.append(node('strong', '', block.ip), document.createElement('br'), node('span', '', `${block.reason}｜至 ${dateText(block.blocked_until)}`));
      const button = node('button', '', '解除');
      button.type = 'button';
      button.addEventListener('click', async () => {
        try {
          await api('/admin/api/security/unblock', {method: 'POST', body: JSON.stringify({ip: block.ip})});
          await loadDashboard('IP 封鎖已解除。');
        } catch (error) { showError(error); }
      });
      row.append(copy, button);
      target.appendChild(row);
    });
  }

  function renderFlags(config) {
    const target = document.querySelector('#security-flags');
    clear(target);
    [
      ['Session 綁定 IP', config.session_ip_binding],
      ['金流驗簽', config.payment_signature_configured],
      ['LINE 驗簽', config.line_signature_configured],
      ['後台 IP 白名單', config.allowlist_required]
    ].forEach(([label, enabled]) => target.appendChild(node('span', `security-flag ${enabled ? 'good' : 'warn'}`, `${label} ${enabled ? '✓' : '待設定'}`)));
  }

  function render(data) {
    dashboard = data;
    renderMetrics(data.metrics);
    renderRevenue(data.revenue_days);
    renderTrafficSources(data.traffic_sources || []);
    renderIntegrations(data.integration_status || {});
    renderIdeas(data.ideas);
    renderOrders(data.orders);
    renderEvents(data.security_events, '#security-events');
    renderBlocks(data.blocked_ips);
    renderEvents(data.audit_logs, '#audit-logs', true);
    renderFlags(data.security_config);
    document.querySelector('#global-price').value = data.global_price;
  }

  function showError(error) {
    status.textContent = error.message || '操作失敗';
    status.classList.add('is-error');
  }

  async function loadDashboard(message = '') {
    status.textContent = message || '正在讀取本機資料…';
    status.classList.remove('is-error');
    try {
      dashboard = await api('/admin/api/dashboard');
      render(dashboard);
      status.textContent = message || `已更新・${new Date().toLocaleTimeString('zh-TW')}`;
    } catch (error) { showError(error); }
  }

  document.querySelector('#refresh-dashboard').addEventListener('click', () => loadDashboard());
  document.querySelector('#price-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const price = Number(document.querySelector('#global-price').value);
    try {
      await api('/admin/api/settings/price', {method: 'POST', body: JSON.stringify({price})});
      await loadDashboard(`全站試行價已更新為 ${money(price)}。`);
    } catch (error) { showError(error); }
  });
  document.querySelector('#security-test').addEventListener('click', async () => {
    try {
      await api('/admin/api/security/test', {method: 'POST'});
      await loadDashboard('安全測試事件已寫入。');
    } catch (error) { showError(error); }
  });

  document.querySelectorAll('[data-close-dialog]').forEach((button) => {
    button.addEventListener('click', () => editor.close());
  });
  editor.addEventListener('click', (event) => {
    if (event.target === editor) editor.close();
  });
  editorForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!editorForm.reportValidity()) return;
    const ideaId = Number(document.querySelector('#idea-id').value);
    const editorStatus = document.querySelector('#idea-editor-status');
    const saveButton = editorForm.querySelector('.save-idea');
    const payload = {
      title: document.querySelector('#idea-title').value,
      role: document.querySelector('#idea-role').value,
      seal: document.querySelector('#idea-seal').value,
      accent: document.querySelector('#idea-accent').value,
      sort_order: Number(document.querySelector('#idea-sort-order').value),
      price_override: document.querySelector('#idea-price-override').value || null,
      discipline: document.querySelector('#idea-discipline').value,
      summary: document.querySelector('#idea-summary').value,
      teaser: document.querySelector('#idea-teaser').value,
      paid_content: document.querySelector('#idea-paid-content').value,
      deliverables: document.querySelector('#idea-deliverables').value,
      tags: document.querySelector('#idea-tags').value
    };
    editorStatus.textContent = '正在儲存…';
    saveButton.disabled = true;
    try {
      await api(`/admin/api/ideas/${ideaId}`, {method: 'POST', body: JSON.stringify(payload)});
      editor.close();
      await loadDashboard('仙策內容已儲存並寫入稽核紀錄。');
    } catch (error) {
      editorStatus.textContent = error.message || '儲存失敗';
    } finally {
      saveButton.disabled = false;
    }
  });

  loadDashboard();
})();
