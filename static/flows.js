/* Progressive UX only: no account data, storage, API calls or payment logic. */
(() => {
  const forms = [...document.querySelectorAll('[data-flow-form]')];
  const pending = new WeakMap();
  const restore = (form, message = '') => {
    const state = pending.get(form);
    if (state) {
      clearTimeout(state.timer);
      state.button.disabled = false;
      state.button.textContent = state.label;
      pending.delete(form);
    }
    form.removeAttribute('aria-busy');
    const status = form.querySelector('[data-flow-submit-status]');
    if (status) status.textContent = message;
  };
  forms.forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (event.defaultPrevented) return;
      if (pending.has(form)) { event.preventDefault(); return; }
      const button = event.submitter || form.querySelector('button[type="submit"]');
      if (!button) return;
      const state = {button, label: button.textContent, timer: null};
      pending.set(form, state);
      form.setAttribute('aria-busy', 'true');
      button.disabled = true;
      button.textContent = form.dataset.pendingLabel || '正在處理…';
      const status = form.querySelector('[data-flow-submit-status]');
      if (status) status.textContent = '正在送出，請稍候；這不是完成通知。';
      state.timer = setTimeout(() => restore(form, '頁面尚未繼續。請先確認網路及最新信件或付款狀態，再決定是否重試；請勿重複付款。'), 20000);
    });
  });
  addEventListener('pageshow', () => forms.forEach((form) => restore(form)));
  document.querySelector('[data-flow-error]')?.focus({preventScroll: true});

  const dialog = document.querySelector('[data-flow-image-dialog]');
  if (!dialog || typeof dialog.showModal !== 'function') return;
  const preview = dialog.querySelector('[data-flow-image-preview]');
  const title = dialog.querySelector('#flow-image-title');
  const imageStatus = dialog.querySelector('[data-flow-image-status]');
  let opener = null;
  preview?.addEventListener('load', () => { if (imageStatus) imageStatus.textContent = ''; });
  preview?.addEventListener('error', () => {
    if (!preview.hasAttribute('src')) return;
    preview.hidden = true;
    if (imageStatus) imageStatus.textContent = '大圖目前無法載入。請先確認網路；若仍無法閱讀，關閉大圖後返回已購內容，重新確認登入狀態。';
  });
  document.querySelectorAll('[data-flow-image]').forEach((link) => {
    link.addEventListener('click', (event) => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
      const source = link.querySelector('img');
      if (!source || !preview) return;
      event.preventDefault();
      opener = link;
      preview.hidden = false;
      if (imageStatus) imageStatus.textContent = '正在載入大圖…';
      preview.src = link.href;
      preview.alt = source.alt;
      if (title) title.textContent = source.alt;
      dialog.showModal();
    });
  });
  dialog.querySelector('[data-flow-image-close]')?.addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); });
  dialog.addEventListener('close', () => {
    preview?.removeAttribute('src');
    opener?.focus({preventScroll: true});
  });
})();
