(() => {
  const root = document.querySelector('#admin-root');
  if (!root) return;

  const csrf = document.querySelector('meta[name="admin-csrf"]')?.content || '';
  const status = document.querySelector('#admin-status');
  const editor = document.querySelector('#idea-editor');
  const editorForm = document.querySelector('#idea-editor-form');
  const workspaceTitles = {
    overview: '今日總覽', orders: '交易訂單', ideas: '仙策內容',
    customers: '客戶開通', integrations: '系統串接', security: '安全稽核'
  };
  const orderLabels = {pending: '待付款', paid: '已付款', cancelled: '已取消', refunded: '已退款'};
  const deliveryLabels = {sent: '已寄出', development: '測試交付', failed: '交付失敗', pending: '等待交付'};
  let dashboard = null;
  let orderFilter = 'all';

  const clear = (element) => { while (element?.firstChild) element.removeChild(element.firstChild); };
  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  };
  const money = (value) => `NT$${Number(value || 0).toLocaleString('zh-TW')}`;
  const dateText = (value) => value ? new Date(value).toLocaleString('zh-TW', {hour12: false}) : '—';
  const setBadge = (selector, count) => {
    const badge = document.querySelector(selector);
    if (!badge) return;
    badge.textContent = String(count || 0);
    badge.hidden = !count;
  };

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body) headers.set('Content-Type', 'application/json');
    if ((options.method || 'GET') !== 'GET') headers.set('X-CSRF-Token', csrf);
    const response = await fetch(path, {...options, headers});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `請求失敗 (${response.status})`);
    return data;
  }

  function setWorkspace(name, updateHash = true) {
    const targetName = workspaceTitles[name] ? name : 'overview';
    document.querySelectorAll('[data-admin-panel]').forEach((panel) => {
      const active = panel.dataset.adminPanel === targetName;
      panel.hidden = !active;
      panel.classList.toggle('is-active', active);
    });
    document.querySelectorAll('[data-admin-view]').forEach((button) => {
      const active = button.dataset.adminView === targetName;
      button.classList.toggle('is-active', active);
      if (active) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
    document.querySelector('#workspace-title').textContent = workspaceTitles[targetName];
    document.title = `${workspaceTitles[targetName]}｜天外一筆`;
    if (updateHash && location.hash !== `#${targetName}`) history.replaceState(null, '', `#${targetName}`);
    root.focus({preventScroll: true});
    window.scrollTo({top: 0, behavior: 'smooth'});
  }

  function renderDate() {
    const today = new Date();
    document.querySelector('#today-weekday').textContent = new Intl.DateTimeFormat('zh-TW', {weekday: 'long'}).format(today);
    document.querySelector('#today-date').textContent = new Intl.DateTimeFormat('zh-TW', {month: '2-digit', day: '2-digit'}).format(today);
  }

  function renderMetrics(metrics) {
    const target = document.querySelector('#metric-grid');
    clear(target);
    [
      ['累計營收', money(metrics.revenue), '所有已付款訂單', 'revenue'],
      ['已付款訂單', metrics.paid_orders, `共 ${metrics.total_orders} 筆交易`, 'paid'],
      ['等待付款', metrics.pending_orders, metrics.pending_orders ? '需要留意付款進度' : '目前沒有待處理', metrics.pending_orders ? 'attention' : 'clear'],
      ['瀏覽轉換率', `${metrics.conversion}%`, `${metrics.views} 次有效瀏覽`, 'conversion']
    ].forEach(([label, value, detail, tone]) => {
      const card = node('article', `metric-card tone-${tone}`);
      card.append(node('span', 'metric-label', label), node('strong', '', value), node('small', '', detail));
      target.appendChild(card);
    });
  }

  function integrationItems(config) {
    return [
      {label: '公開官網', value: config.public_https ? '正式 HTTPS' : '尚未使用 HTTPS', ready: config.public_https, detail: config.base_url, key: 'WEB'},
      {label: 'LINE 客服', value: config.line_channel ? '正式頻道已連線' : '尚未設定頻道', ready: config.line_channel, detail: `已接收 ${config.line_events || 0} 筆事件`, key: 'LINE'},
      {label: '付款服務', value: config.payment_label || config.payment_provider, ready: !['mock', 'unavailable'].includes(config.payment_provider), detail: config.payment_provider === 'unavailable' ? '缺少特店憑證或交付設定' : '以伺服器付款通知為準', key: 'PAY'},
      {label: 'Email 交付', value: config.email_delivery ? '寄送服務已啟用' : '尚未啟用寄送', ready: config.email_delivery, detail: '付款後寄送專屬開通資料', key: 'MAIL'}
    ];
  }

  function renderAttention(data) {
    const target = document.querySelector('#attention-list');
    clear(target);
    const pendingAccess = data.customer_access?.summary?.pending_activation || 0;
    const riskEvents = (data.security_events || []).filter((item) => ['critical', 'high'].includes(item.severity)).length;
    const disconnected = integrationItems(data.integration_status || {}).filter((item) => !item.ready).length;
    const items = [
      {count: data.metrics.pending_orders, title: '待付款訂單', detail: '確認付款進度與異常交易', view: 'orders', tone: 'gold'},
      {count: pendingAccess, title: '已付款、尚未開通', detail: '確認開通資料是否順利交付', view: 'customers', tone: 'jade'},
      {count: disconnected, title: '串接尚未就緒', detail: '上線前完成必要服務設定', view: 'integrations', tone: 'violet'},
      {count: riskEvents, title: '高風險安全事件', detail: '檢查拒絕與封鎖紀錄', view: 'security', tone: 'red'}
    ].filter((item) => item.count > 0);
    const total = items.reduce((sum, item) => sum + item.count, 0);
    document.querySelector('#attention-total').textContent = String(total);
    setBadge('#nav-attention-count', total);
    setBadge('#nav-order-count', data.metrics.pending_orders);
    setBadge('#nav-customer-count', pendingAccess);
    document.querySelector('#risk-event-count').textContent = String(riskEvents);
    if (!items.length) {
      const empty = node('div', 'attention-empty');
      empty.append(node('i', '', '✓'), node('strong', '', '目前沒有待處理項目'), node('span', '', '所有主要營運狀態都在正常範圍內。'));
      target.appendChild(empty);
      return;
    }
    items.forEach((item) => {
      const button = node('button', `attention-item tone-${item.tone}`);
      button.type = 'button';
      const count = node('strong', '', item.count);
      const copy = node('span');
      copy.append(node('b', '', item.title), node('small', '', item.detail));
      button.append(count, copy, node('i', '', '→'));
      button.addEventListener('click', () => setWorkspace(item.view));
      target.appendChild(button);
    });
  }

  function renderPulse(data) {
    const target = document.querySelector('#business-pulse');
    clear(target);
    const summary = data.customer_access?.summary || {};
    [
      ['有效瀏覽', data.metrics.views, '近站內累計'],
      ['付費客戶', summary.paid_customers || 0, '不重複 Email'],
      ['已開通內容', summary.activated_entitlements || 0, `共 ${summary.paid_entitlements || 0} 份權限`],
      ['目前登入客戶', summary.active_sessions || 0, '有效工作階段']
    ].forEach(([label, value, detail]) => {
      const row = node('div', 'pulse-row');
      const copy = node('span');
      copy.append(node('b', '', label), node('small', '', detail));
      row.append(copy, node('strong', '', value));
      target.appendChild(row);
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
      wrapper.append(node('strong', '', money(item.amount)), progress, node('span', '', item.key.slice(5)));
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
      const track = node('div', 'traffic-track');
      const bar = node('i');
      bar.style.width = `${Math.max(4, (Number(item.count || 0) / total) * 100)}%`;
      track.appendChild(bar);
      row.append(node('span', '', item.source || '其他'), track, node('strong', '', item.count));
      target.appendChild(row);
    });
  }

  function renderIntegrations(config) {
    const target = document.querySelector('#integration-grid');
    clear(target);
    const items = integrationItems(config);
    const ready = items.filter((item) => item.ready).length;
    const summary = document.querySelector('#integration-summary');
    clear(summary);
    summary.className = `integration-summary ${ready === items.length ? 'ready' : 'pending'}`;
    summary.append(node('i', '', ready === items.length ? '✓' : '!'), node('strong', '', `${ready} / ${items.length} 項已就緒`), node('span', '', ready === items.length ? '主要外部服務均可用。' : '仍有服務需要設定或驗收。'));
    items.forEach((item) => {
      const card = node('article', `integration-card ${item.ready ? 'ready' : 'pending'}`);
      const head = node('div', 'integration-card-head');
      head.append(node('i', '', item.key), node('span', `integration-dot ${item.ready ? 'good' : 'warn'}`, item.ready ? '已就緒' : '待設定'));
      card.append(head, node('h3', '', item.label), node('strong', '', item.value), node('small', '', item.detail));
      target.appendChild(card);
    });
  }

  function setEditorValue(id, value) {
    const input = document.querySelector(id);
    if (input) input.value = value ?? '';
  }

  function openIdeaEditor(idea) {
    const fields = {
      id: 'id', title: 'title', role: 'role', seal: 'seal', accent: 'accent',
      'sort-order': 'sort_order', 'price-override': 'price_override', discipline: 'discipline',
      summary: 'summary', teaser: 'teaser', 'paid-content': 'paid_content',
      deliverables: 'deliverables', tags: 'tags'
    };
    Object.entries(fields).forEach(([field, key]) => setEditorValue(`#idea-${field}`, idea[key]));
    document.querySelector('#idea-editor-slug').textContent = `內容識別：${idea.slug}`;
    document.querySelector('#idea-editor-status').textContent = '';
    editor.showModal();
    document.querySelector('#idea-title').focus();
  }

  function renderIdeas(ideas) {
    const target = document.querySelector('#idea-admin-list');
    clear(target);
    document.querySelector('#published-count').textContent = `${ideas.filter((idea) => idea.published).length} / ${ideas.length} 已上架`;
    ideas.forEach((idea) => {
      const row = node('article', `idea-admin-row accent-${idea.accent}`);
      const seal = node('span', 'idea-admin-seal', idea.seal);
      const copy = node('div', 'idea-admin-copy');
      copy.append(node('strong', '', idea.title), node('small', '', `${idea.role}・${idea.discipline}`));
      const price = node('div', 'idea-admin-price');
      price.append(node('strong', '', money(idea.price)), node('small', '', idea.price_override === null ? '套用預設價' : '單獨定價'));
      const toggle = node('button', `publish-toggle ${idea.published ? 'on' : ''}`, idea.published ? '已上架' : '已隱藏');
      toggle.type = 'button';
      toggle.setAttribute('aria-pressed', String(idea.published));
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
      row.append(seal, copy, price, actions);
      target.appendChild(row);
    });
  }

  function visibleOrders() {
    const query = document.querySelector('#order-search').value.trim().toLowerCase();
    return (dashboard?.orders || []).filter((order) => {
      const statusMatch = orderFilter === 'all' || order.status === orderFilter || (orderFilter === 'closed' && ['cancelled', 'refunded'].includes(order.status));
      const haystack = [order.order_no, order.title, order.role, order.customer_name, order.customer_email].join(' ').toLowerCase();
      return statusMatch && (!query || haystack.includes(query));
    });
  }

  function renderOrders() {
    const orders = dashboard?.orders || [];
    const target = document.querySelector('#orders-table');
    clear(target);
    const filtered = visibleOrders();
    const counts = {
      all: orders.length,
      pending: orders.filter((item) => item.status === 'pending').length,
      paid: orders.filter((item) => item.status === 'paid').length,
      closed: orders.filter((item) => ['cancelled', 'refunded'].includes(item.status)).length
    };
    Object.entries(counts).forEach(([key, count]) => { document.querySelector(`#order-count-${key}`).textContent = String(count); });
    document.querySelector('#order-result-summary').textContent = `顯示 ${filtered.length} 筆，共載入最近 ${orders.length} 筆訂單`;
    if (!filtered.length) {
      const row = node('tr');
      const cell = node('td', 'table-empty', '找不到符合條件的訂單');
      cell.colSpan = 6;
      row.appendChild(cell);
      target.appendChild(row);
      return;
    }
    filtered.forEach((order) => {
      const row = node('tr');
      const orderNo = node('td', 'order-number');
      orderNo.append(node('strong', '', order.order_no), node('small', '', order.paid_at ? `付款 ${dateText(order.paid_at)}` : '尚未付款'));
      const product = node('td');
      product.append(node('strong', '', order.title), node('small', '', order.role));
      const customer = node('td');
      customer.append(node('strong', '', order.customer_name), node('small', '', order.customer_email));
      const statusCell = node('td');
      statusCell.appendChild(node('span', `status-pill ${order.status}`, orderLabels[order.status] || order.status));
      row.append(orderNo, product, customer, node('td', 'money-cell', money(order.amount)), statusCell, node('td', 'date-cell', dateText(order.created_at)));
      target.appendChild(row);
    });
  }

  function renderCustomerAccess(data) {
    const target = document.querySelector('#customer-metrics');
    const summary = data?.summary || {};
    clear(target);
    [
      ['付費客戶', summary.paid_customers || 0, '不重複客戶'],
      ['內容權限', summary.paid_entitlements || 0, '已付款份數'],
      ['已完成開通', summary.activated_entitlements || 0, '可登入取用'],
      ['等待開通', summary.pending_activation || 0, '需要確認交付'],
      ['目前登入', summary.active_sessions || 0, '有效工作階段']
    ].forEach(([label, value, detail], index) => {
      const card = node('article', `customer-metric ${index === 3 && value ? 'needs-attention' : ''}`);
      card.append(node('span', '', label), node('strong', '', value), node('small', '', detail));
      target.appendChild(card);
    });
    const table = document.querySelector('#customer-access-table');
    clear(table);
    if (!data?.orders?.length) {
      const row = node('tr');
      const cell = node('td', 'table-empty', '目前沒有已付款客戶');
      cell.colSpan = 6;
      row.appendChild(cell);
      table.appendChild(row);
      return;
    }
    data.orders.forEach((order) => {
      const row = node('tr');
      const customer = node('td');
      customer.append(node('strong', '', order.customer_name), node('small', '', order.customer_email));
      const delivery = node('td');
      delivery.appendChild(node('span', `status-pill delivery-${order.delivery_status}`, deliveryLabels[order.delivery_status] || '等待交付'));
      const activation = node('td');
      activation.appendChild(node('span', `status-pill ${order.activated ? 'paid' : 'pending'}`, order.activated ? '已開通' : '待開通'));
      row.append(customer, node('td', '', order.title), node('td', 'order-number', order.order_no), delivery, activation, node('td', 'date-cell', dateText(order.paid_at)));
      table.appendChild(row);
    });
  }

  function eventItem(item, audit = false) {
    const row = node('article', `event-item severity-${item.severity || 'info'}`);
    const copy = node('div');
    copy.append(node('strong', '', audit ? item.action : item.event_type), node('span', '', audit ? `${item.target}・${item.detail}` : `${item.action_taken}・${item.path}`));
    row.append(copy, node('small', '', audit ? item.ip : item.ip), node('time', '', dateText(item.created_at)));
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
      const row = node('article', 'event-item block-item');
      const copy = node('div');
      copy.append(node('strong', '', block.ip), node('span', '', `${block.reason}・至 ${dateText(block.blocked_until)}`));
      const button = node('button', '', '解除封鎖');
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
      ['後台工作階段綁定', config.session_ip_binding, '降低 Cookie 遭竊風險'],
      ['金流通知驗簽', config.payment_signature_configured, '確認付款來源'],
      ['LINE 事件驗簽', config.line_signature_configured, '拒絕偽造訊息'],
      ['後台 IP 白名單', config.allowlist_required, '限制可登入來源']
    ].forEach(([label, enabled, detail]) => {
      const card = node('article', `security-flag ${enabled ? 'good' : 'warn'}`);
      card.append(node('i', '', enabled ? '✓' : '!'), node('strong', '', label), node('small', '', enabled ? detail : `${detail}・待設定`));
      target.appendChild(card);
    });
  }

  function render(data) {
    dashboard = data;
    renderMetrics(data.metrics);
    renderAttention(data);
    renderPulse(data);
    renderRevenue(data.revenue_days || []);
    renderTrafficSources(data.traffic_sources || []);
    renderIntegrations(data.integration_status || {});
    renderIdeas(data.ideas || []);
    renderOrders();
    renderCustomerAccess(data.customer_access || {});
    renderEvents(data.security_events || [], '#security-events');
    renderBlocks(data.blocked_ips || []);
    renderEvents(data.audit_logs || [], '#audit-logs', true);
    renderFlags(data.security_config || {});
    document.querySelector('#global-price').value = data.global_price;
  }

  function showError(error) {
    status.textContent = error.message || '操作失敗，請稍後再試。';
    status.classList.add('is-error');
  }

  async function loadDashboard(message = '') {
    status.textContent = message || '正在讀取營運資料…';
    status.classList.remove('is-error');
    try {
      render(await api('/admin/api/dashboard'));
      status.textContent = message || `資料已更新・${new Date().toLocaleTimeString('zh-TW', {hour12: false})}`;
    } catch (error) { showError(error); }
  }

  document.querySelectorAll('[data-admin-view]').forEach((button) => button.addEventListener('click', () => setWorkspace(button.dataset.adminView)));
  document.querySelector('[data-admin-link]')?.addEventListener('click', (event) => { event.preventDefault(); setWorkspace('overview'); });
  window.addEventListener('hashchange', () => setWorkspace(location.hash.slice(1), false));
  document.querySelector('#refresh-dashboard').addEventListener('click', () => loadDashboard());
  document.querySelector('#order-search').addEventListener('input', renderOrders);
  document.querySelectorAll('[data-order-filter]').forEach((button) => {
    button.addEventListener('click', () => {
      orderFilter = button.dataset.orderFilter;
      document.querySelectorAll('[data-order-filter]').forEach((item) => item.classList.toggle('is-active', item === button));
      renderOrders();
    });
  });
  document.querySelector('#price-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const price = Number(document.querySelector('#global-price').value);
    try {
      await api('/admin/api/settings/price', {method: 'POST', body: JSON.stringify({price})});
      await loadDashboard(`全站預設價格已更新為 ${money(price)}。`);
    } catch (error) { showError(error); }
  });
  document.querySelector('#security-test').addEventListener('click', async () => {
    try {
      await api('/admin/api/security/test', {method: 'POST'});
      await loadDashboard('安全測試事件已寫入。');
    } catch (error) { showError(error); }
  });
  document.querySelectorAll('[data-close-dialog]').forEach((button) => button.addEventListener('click', () => editor.close()));
  editor.addEventListener('click', (event) => { if (event.target === editor) editor.close(); });
  editorForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!editorForm.reportValidity()) return;
    const ideaId = Number(document.querySelector('#idea-id').value);
    const editorStatus = document.querySelector('#idea-editor-status');
    const saveButton = editorForm.querySelector('.save-idea');
    const payload = {
      title: document.querySelector('#idea-title').value, role: document.querySelector('#idea-role').value,
      seal: document.querySelector('#idea-seal').value, accent: document.querySelector('#idea-accent').value,
      sort_order: Number(document.querySelector('#idea-sort-order').value), price_override: document.querySelector('#idea-price-override').value || null,
      discipline: document.querySelector('#idea-discipline').value, summary: document.querySelector('#idea-summary').value,
      teaser: document.querySelector('#idea-teaser').value, paid_content: document.querySelector('#idea-paid-content').value,
      deliverables: document.querySelector('#idea-deliverables').value, tags: document.querySelector('#idea-tags').value
    };
    editorStatus.textContent = '正在儲存…';
    saveButton.disabled = true;
    try {
      await api(`/admin/api/ideas/${ideaId}`, {method: 'POST', body: JSON.stringify(payload)});
      editor.close();
      await loadDashboard('仙策內容已儲存並寫入稽核紀錄。');
    } catch (error) { editorStatus.textContent = error.message || '儲存失敗'; }
    finally { saveButton.disabled = false; }
  });

  renderDate();
  setWorkspace(location.hash.slice(1) || 'overview', false);
  loadDashboard();
})();
