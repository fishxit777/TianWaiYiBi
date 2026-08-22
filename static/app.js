(() => {
  const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || '';

  document.querySelectorAll('[data-filter]').forEach((button) => {
    button.addEventListener('click', () => {
      const filter = button.dataset.filter || 'all';
      document.querySelectorAll('[data-filter]').forEach((item) => item.classList.remove('is-active'));
      button.classList.add('is-active');
      document.querySelectorAll('.idea-card').forEach((card) => {
        const visible = filter === 'all' || (card.dataset.tags || '').includes(filter);
        card.classList.toggle('is-hidden', !visible);
      });
      fetch('/api/events', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf()},
        body: JSON.stringify({event_name: 'filter_used', source: 'web'})
      }).catch(() => {});
    });
  });

  document.querySelectorAll('[data-line-cta]').forEach((link) => {
    link.addEventListener('click', () => {
      fetch('/api/events', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf()},
        body: JSON.stringify({event_name: 'line_cta_clicked', source: 'web'}),
        keepalive: true
      }).catch(() => {});
    });
  });

  const copyLineId = document.querySelector('[data-copy-line-id]');
  if (copyLineId) {
    copyLineId.addEventListener('click', async () => {
      const accountId = copyLineId.dataset.copyLineId || '@279plitu';
      const status = document.querySelector('#copy-line-status');
      try {
        await navigator.clipboard.writeText(accountId);
        status.textContent = `${accountId} 已抄錄，可到 LINE 搜尋仙策靈使。`;
        copyLineId.textContent = '名號已抄錄';
      } catch (_error) {
        status.textContent = `請手動抄錄仙策靈使名號：${accountId}`;
      }
    });
  }

  const orderForm = document.querySelector('#order-form');
  if (orderForm) {
    const noticeDialog = document.querySelector('#purchase-notice-dialog');
    const noticeError = document.querySelector('#purchase-notice-error');
    const confirmPurchase = document.querySelector('[data-confirm-purchase]');

    confirmPurchase?.addEventListener('click', () => {
      const purchaseConsent = orderForm.querySelector('[name="purchase_notice_consent"]');
      const digitalConsent = orderForm.querySelector('[name="digital_content_consent"]');
      if (!purchaseConsent?.checked || !digitalConsent?.checked) {
        noticeError.textContent = '請勾選兩項確認後再繼續付款。';
        return;
      }
      noticeError.textContent = '';
      orderForm.dataset.noticeApproved = 'true';
      noticeDialog?.close();
      orderForm.requestSubmit();
    });

    orderForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const status = document.querySelector('#order-status');
      const submit = orderForm.querySelector('button[type="submit"]');
      const nameInput = orderForm.querySelector('[name="customer_name"]');
      const emailInput = orderForm.querySelector('[name="customer_email"]');
      if (!nameInput.reportValidity() || !emailInput.reportValidity()) return;
      if (orderForm.dataset.noticeApproved !== 'true') {
        if (typeof noticeDialog?.showModal === 'function') noticeDialog.showModal();
        else noticeDialog?.setAttribute('open', '');
        return;
      }
      orderForm.dataset.noticeApproved = 'false';
      status.textContent = '正在建立訂單…';
      submit.disabled = true;
      try {
        const form = new FormData(orderForm);
        const response = await fetch('/api/orders', {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf()},
          body: JSON.stringify({
            idea_slug: orderForm.dataset.ideaSlug,
            customer_name: form.get('customer_name'),
            customer_email: form.get('customer_email'),
            purchase_notice_consent: form.get('purchase_notice_consent') === 'on',
            digital_content_consent: form.get('digital_content_consent') === 'on'
          })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '建立訂單失敗');
        status.textContent = `訂單 ${data.order_no} 已建立，正在前往付款…`;
        window.location.assign(data.checkout_url);
      } catch (error) {
        status.textContent = error.message || '建立訂單失敗，請稍後再試。';
        submit.disabled = false;
      }
    });
  }

  document.querySelectorAll('[data-dialog-close]').forEach((button) => {
    button.addEventListener('click', () => button.closest('dialog')?.close());
  });

  document.querySelectorAll('dialog[data-auto-modal]').forEach((dialog) => {
    if (typeof dialog.showModal !== 'function') return;
    if (dialog.open) dialog.close();
    window.setTimeout(() => dialog.showModal(), 80);
  });

  const paymentForm = document.querySelector('[data-auto-submit-payment]');
  if (paymentForm) window.setTimeout(() => paymentForm.requestSubmit(), 350);

  const simulator = document.querySelector('#line-simulator-form');
  if (simulator) {
    const sendSimulatorMessage = async (message) => {
      const input = simulator.querySelector('input[name="message"]');
      if (!message) return;
      const log = document.querySelector('#chat-log');
      const userBubble = document.createElement('div');
      userBubble.className = 'bubble user';
      userBubble.textContent = message;
      log.appendChild(userBubble);
      input.value = '';
      try {
        const response = await fetch('/dev/line/reply', {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf()},
          body: JSON.stringify({message})
        });
        const data = await response.json();
        const botBubble = document.createElement('div');
        botBubble.className = 'bubble bot';
        const textMessages = (data.messages || []).filter((item) => item.type === 'text').map((item) => item.text);
        botBubble.textContent = textMessages.join('\n\n') || data.reply || data.error || '仙策靈使暫時沒有回應。';
        log.appendChild(botBubble);
        if (Array.isArray(data.cards) && data.cards.length) {
          const carousel = document.createElement('div');
          carousel.className = 'line-card-carousel';
          data.cards.forEach((card) => {
            const article = document.createElement('article');
            article.className = 'line-product-card';
            article.style.setProperty('--line-accent', card.color || '#348F8A');
            const eyebrow = document.createElement('span');
            eyebrow.textContent = card.eyebrow || '仙策';
            const role = document.createElement('strong');
            role.textContent = card.role || '';
            const title = document.createElement('h3');
            title.textContent = card.title || '';
            const summary = document.createElement('p');
            summary.textContent = card.summary || '';
            const footer = document.createElement('div');
            const price = document.createElement('b');
            price.textContent = card.price || '';
            const link = document.createElement('a');
            link.href = card.url || '#';
            link.textContent = '翻閱摘要';
            footer.append(price, link);
            article.append(eyebrow, role, title, summary, footer);
            carousel.appendChild(article);
          });
          log.appendChild(carousel);
        }
        log.scrollTop = log.scrollHeight;
      } catch (_error) {
        const botBubble = document.createElement('div');
        botBubble.className = 'bubble bot';
        botBubble.textContent = '本機連線中斷，請確認服務仍在運行。';
        log.appendChild(botBubble);
      }
    };
    simulator.addEventListener('submit', async (event) => {
      event.preventDefault();
      const input = simulator.querySelector('input[name="message"]');
      await sendSimulatorMessage(input.value.trim());
    });
    document.querySelectorAll('[data-line-command]').forEach((button) => {
      button.addEventListener('click', () => sendSimulatorMessage(button.dataset.lineCommand || ''));
    });
  }
})();
