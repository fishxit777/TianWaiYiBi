(() => {
  const hub = document.querySelector('#release-hub');
  if (!hub) return;
  const target = document.querySelector('#release-cards');
  const summary = document.querySelector('#release-summary');
  const status = document.querySelector('#release-status');
  const publishAll = document.querySelector('#release-publish-all');
  const refresh = document.querySelector('#release-refresh');
  const csrf = document.querySelector('meta[name="admin-csrf"]')?.content || '';
  let catalog = null;
  let busy = false;
  let loading = false;
  let loadVersion = 0;
  const money = value => `NT$${Number(value).toLocaleString('zh-TW')}`;
  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const isListed = card => card.commerce?.price_visible === true;
  function availability() {
    publishAll.disabled = busy || loading || !catalog?.can_publish_all || catalog.cards.every(isListed);
    refresh.disabled = busy || loading;
    hub.querySelectorAll('[data-publish-package]').forEach(button => {
      const card = catalog?.cards.find(item => String(item.id) === button.dataset.publishPackage);
      button.disabled = busy || loading || !card?.package_status?.ready || isListed(card);
    });
  }
  async function api(path, options = {}) {
    const response = await fetch(path, {credentials: 'same-origin', cache: 'no-store', ...options,
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf, ...(options.headers || {})}});
    const result = await response.json().catch(() => ({}));
    if (!response.ok || result.ok !== true) throw new Error(result.error || '內容包服務暫時無法使用，請重新核對。');
    return result;
  }
  function render() {
    target.replaceChildren();
    summary.textContent = `${catalog.counts.ready} / ${catalog.counts.total} 案圖文與售價已備妥；${catalog.counts.listed} 案已公開售價。第十四案不在本次定價批次。`;
    catalog.cards.forEach(card => {
      const row = node('article', 'release-card');
      row.dataset.releaseId = card.id;
      const cover = node('img', 'release-card-cover');
      cover.src = `/admin/ideas/${card.id}/assets/hero`;
      cover.alt = `${card.public_title}・私密概念主視覺`;
      cover.loading = 'lazy';
      cover.decoding = 'async';
      const body = node('div', 'release-card-body');
      body.append(node('span', 'release-card-kicker', card.public_title), node('h4', '', card.title));
      body.append(node('p', 'release-card-scope', card.package?.scope || '內容包仍待整理。'));
      const counts = card.package_status?.counts || {};
      body.append(node('p', 'release-card-facts', `${counts.figures || 0} 張圖・原始完整文字・${counts.flow_steps || 0} 步流程・${counts.mvp_steps || 0} 步 MVP\n${counts.tests || 0} 項測試・${counts.worksheets || 0} 份工作表・交接清單`));
      body.append(node('strong', 'release-card-price', card.prepared_price ? money(card.prepared_price) : '售價待備妥'));
      const label = isListed(card) ? (card.commerce.can_purchase ? '已上架・可購買' : '已上架・收款尚未開放') : (card.package_status?.ready ? '圖文與售價已備妥・等待你上架' : '尚有缺項・暫不能上架');
      body.append(node('p', 'release-card-state', label));
      if (card.package_status?.gaps?.length) {
        const gaps = node('ul', 'release-gaps');
        card.package_status.gaps.forEach(gap => gaps.append(node('li', '', gap)));
        body.append(gaps);
      }
      const actions = node('div', 'release-card-actions');
      const preview = node('a', 'release-preview-link', '完整圖文預覽');
      preview.href = card.preview_url;
      preview.setAttribute('aria-label', `${card.public_title}：完整圖文預覽`);
      const publish = node('button', 'release-publish-button', isListed(card) ? '已上架' : '上架');
      publish.type = 'button';
      publish.dataset.publishPackage = card.id;
      publish.setAttribute('aria-label', `${card.public_title}：${isListed(card) ? '已上架' : '上架'}`);
      publish.addEventListener('click', () => publishPackages(card.publish_url, card.public_title));
      actions.append(preview, publish);
      body.append(actions);
      row.append(cover, body);
      target.append(row);
    });
    availability();
  }
  async function load(message = '') {
    const version = ++loadVersion;
    loading = true;
    availability();
    try {
      const result = await api('/admin/api/release-packages');
      if (version !== loadVersion) return;
      if (!Array.isArray(result.cards) || result.cards.length !== 13 || !result.counts) throw new Error('未取得完整十三案清單，上架已暫停。');
      catalog = result;
      render();
      status.textContent = message || '價格只在後台備妥；按上架前，不會公開新售價。';
      status.classList.remove('is-error');
    } catch (error) {
      if (version !== loadVersion) return;
      catalog = null;
      availability();
      status.textContent = /fetch|network/i.test(error.message) ? '連線未完成，上架已暫停；請重新核對。' : error.message;
      status.classList.add('is-error');
    } finally {
      if (version === loadVersion) { loading = false; availability(); }
    }
  }
  async function publishPackages(path, label) {
    if (busy || loading || !catalog) return;
    busy = true;
    availability();
    status.classList.remove('is-error');
    status.textContent = `正在核對並上架${label}…`;
    try {
      const result = await api(path, {method: 'POST', body: JSON.stringify({confirm_publication: true})});
      if (!Number.isInteger(result.published_count)) throw new Error('上架回應不完整，請先重新核對，不要重複送出。');
      await load(`${result.published_count} 案上架完成。公開封印線索與售價；完整圖文仍受權限保護，沒有解除收款限制。`);
    } catch (error) {
      status.textContent = `${error.message} 請先按「重新核對內容包」查看目前狀態，再決定是否重試。`;
      status.classList.add('is-error');
      catalog = null;
    } finally { busy = false; availability(); }
  }
  publishAll.addEventListener('click', () => {
    if (!publishAll.disabled) publishPackages('/admin/api/release-packages/publish', '十三案');
  });
  refresh.addEventListener('click', () => { if (!busy) load(); });
  load();
})();
