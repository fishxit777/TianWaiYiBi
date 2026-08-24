(() => {
  const widgets = document.querySelectorAll('[data-conversation-widget]');
  if (!widgets.length) return;

  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const colorKeys = new Set(['keeper', 'jade', 'gold', 'azure', 'violet', 'coral', 'silver']);
  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const formatTime = (value) => {
    if (!value) return '';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value.slice(0, 16).replace('T', ' ');
    return new Intl.DateTimeFormat('zh-TW', {month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'}).format(parsed);
  };
  const activityStorageKey = (slug, visibility, scope = 'public') => `twyb:idea-transmission-seen:${slug}:${visibility}:${visibility === 'private' ? scope : 'public'}`;
  const markActivitySeen = (slug, visibility, marker, scope = 'public') => {
    if (!slug || !Number(marker)) return;
    try {
      localStorage.setItem(activityStorageKey(slug, visibility, scope), String(marker));
      window.dispatchEvent(new CustomEvent('twyb:conversation-seen', {detail: {slug, visibility}}));
    } catch (_error) {
      // The conversation remains usable when storage is unavailable.
    }
  };

  widgets.forEach((widget) => {
    const trigger = widget.querySelector('[data-conversation-trigger]');
    const triggerLabel = widget.querySelector('[data-conversation-trigger-label]');
    const panel = widget.querySelector('[data-conversation-panel]');
    const tabs = [...widget.querySelectorAll('[data-conversation-tab]')];
    const privacy = widget.querySelector('[data-conversation-privacy-note]');
    const privacyCopy = widget.querySelector('[data-conversation-privacy-copy]');
    const status = widget.querySelector('[data-conversation-status]');
    const timeline = widget.querySelector('[data-conversation-messages]');
    const form = widget.querySelector('[data-conversation-form]');
    const textarea = form.querySelector('textarea');
    const honeypot = form.querySelector('input[name="website"]');
    const formLabel = form.querySelector('[data-conversation-form-label]');
    const count = form.querySelector('[data-conversation-count]');
    const limit = form.querySelector('[data-conversation-limit]');
    const visitorCheck = form.querySelector('[data-conversation-visitor-check]');
    const turnstileMount = form.querySelector('[data-conversation-turnstile]');
    const loginNote = widget.querySelector('[data-conversation-login-note]');
    const loginCopy = widget.querySelector('[data-conversation-login-copy]');
    const viewerKey = widget.querySelector('[data-conversation-viewer-key]');
    const sectionKey = widget.dataset.sectionKey;
    const ideaSlug = widget.dataset.ideaSlug || '';
    let visibility = 'public';
    let loaded = false;
    let controller = null;
    let viewerState = {authenticated: false, visitor_submission_enabled: false};
    let turnstileWidgetId = null;
    let turnstileToken = '';
    let turnstileWaits = 0;
    let turnstileTimer = null;

    const endpoint = () => {
      const query = new URLSearchParams({visibility});
      if (ideaSlug) query.set('idea_slug', ideaSlug);
      return `/api/conversations/${encodeURIComponent(sectionKey)}?${query}`;
    };
    const applyIdentity = (node, color) => {
      node.dataset.identityColor = colorKeys.has(color) ? color : 'silver';
    };
    const renderMessage = (message) => {
      const card = element('article', 'conversation-message');
      applyIdentity(card, message.author?.color);
      if (message.mine) card.classList.add('is-mine');
      if (message.status === 'pending') card.classList.add('is-pending');
      const avatar = element('span', 'conversation-avatar');
      avatar.setAttribute('aria-hidden', 'true');
      avatar.textContent = message.author?.label === '守閣者' ? '守' : (message.author?.label || '同道').slice(-2);
      const content = element('div', 'conversation-message-content');
      const header = element('header', 'conversation-message-meta');
      const identity = element('div', 'conversation-message-identity');
      identity.append(element('strong', '', message.author?.label || '同道'));
      (message.badges || []).forEach((badge) => identity.append(element('span', '', badge)));
      if (message.target?.alias) {
        const target = element('small', 'conversation-target', `回覆 ${message.target.alias}`);
        applyIdentity(target, message.target.color);
        identity.append(target);
      }
      header.append(identity, element('time', '', formatTime(message.created_at)));
      content.append(header, element('p', 'conversation-message-body', message.body || ''));
      card.append(avatar, content);
      return card;
    };
    const renderEmpty = () => {
      const empty = element('div', 'conversation-empty');
      const visitorCanPost = !viewerState.authenticated && viewerState.visitor_submission_enabled;
      empty.append(
        element('span', '', visibility === 'public' ? '◇' : '封'),
        element('strong', '', visibility === 'public' ? '此卷尚無公開傳音' : '這裡還沒有私密對話'),
        element('p', '', visibility === 'public'
          ? (visitorCanPost ? '不必登入，也可以匿名留下第一道回聲。' : '已購客戶登入後可以留下第一道回聲。')
          : '只有你與守閣者能看見這裡的內容。')
      );
      timeline.append(empty);
    };
    const resetTurnstile = () => {
      turnstileToken = '';
      if (turnstileWidgetId !== null && window.turnstile?.reset) {
        try { window.turnstile.reset(turnstileWidgetId); } catch (_error) { /* retry on next render */ }
      }
    };
    const ensureTurnstile = () => {
      if (visitorCheck.hidden || !turnstileMount?.dataset.sitekey || turnstileWidgetId !== null) return;
      if (!window.turnstile?.render) {
        turnstileWaits += 1;
        if (turnstileWaits <= 40) {
          clearTimeout(turnstileTimer);
          turnstileTimer = setTimeout(ensureTurnstile, 250);
        } else {
          status.textContent = '訪客安全確認暫時無法載入，請稍後重新整理。';
        }
        return;
      }
      try {
        turnstileWidgetId = window.turnstile.render(turnstileMount, {
          sitekey: turnstileMount.dataset.sitekey,
          action: turnstileMount.dataset.action,
          theme: 'dark',
          language: 'zh-tw',
          size: window.matchMedia('(max-width: 480px)').matches ? 'compact' : 'flexible',
          callback: (token) => { turnstileToken = token || ''; },
          'expired-callback': () => { turnstileToken = ''; },
          'error-callback': () => {
            turnstileToken = '';
            status.textContent = '訪客安全確認未完成，請稍後重試。';
          }
        });
      } catch (_error) {
        turnstileWidgetId = null;
        status.textContent = '訪客安全確認暫時無法載入，請稍後重新整理。';
      }
    };
    const updateViewer = (viewer) => {
      viewerState = viewer || {authenticated: false, visitor_submission_enabled: false};
      const authenticated = Boolean(viewerState.authenticated);
      const visitorCanPost = !authenticated && visibility === 'public' && Boolean(viewerState.visitor_submission_enabled);
      form.hidden = !(authenticated || visitorCanPost);
      visitorCheck.hidden = !visitorCanPost;
      loginNote.hidden = authenticated || visitorCanPost;
      if (authenticated || viewerState.alias) {
        viewerKey.hidden = false;
        applyIdentity(viewerKey, viewerState.color);
        viewerKey.querySelector('b').textContent = `${viewerState.alias}（你）`;
      } else {
        viewerKey.hidden = true;
      }
      if (!loginNote.hidden) {
        loginCopy.textContent = visibility === 'private'
          ? '私密傳音只開放已驗證客戶，登入後即可開啟。'
          : '訪客留言目前暫停；已購客戶登入後仍可公開留言。';
      }
      const maxLength = visitorCanPost ? 500 : 800;
      textarea.maxLength = maxLength;
      limit.textContent = String(maxLength);
      formLabel.textContent = visibility === 'public'
        ? (visitorCanPost ? '匿名留下公開傳音' : '留下公開傳音')
        : '只給守閣者的私密傳音';
      textarea.placeholder = visibility === 'public'
        ? '寫下你的想法或疑問；請勿放入個人資料、網址或 HTML。'
        : '只有你與守閣者能看見；仍請勿輸入密碼、驗證碼或付款資料。';
      if (visitorCanPost) ensureTurnstile();
    };
    const showLoginRequired = () => {
      timeline.replaceChildren();
      const empty = element('div', 'conversation-empty conversation-empty-private');
      empty.append(element('span', '', '封'), element('strong', '', '登入後開啟私密傳音'), element('p', '', '此處不會向其他訪客顯示，也不使用顏色代替權限。'));
      timeline.append(empty);
      form.hidden = true;
      visitorCheck.hidden = true;
      loginCopy.textContent = '私密傳音只開放已驗證客戶，登入後即可開啟。';
      loginNote.hidden = false;
      status.textContent = '私密傳音需要客戶身分驗證。';
    };
    const loadMessages = async () => {
      controller?.abort();
      controller = new AbortController();
      status.textContent = '正在讀取這一卷的傳音…';
      timeline.setAttribute('aria-busy', 'true');
      try {
        const response = await fetch(endpoint(), {credentials: 'same-origin', headers: {'Accept': 'application/json'}, signal: controller.signal});
        if (response.status === 401 && visibility === 'private') {
          showLoginRequired();
          return;
        }
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '目前無法讀取傳音');
        updateViewer(data.viewer);
        timeline.replaceChildren();
        (data.messages || []).forEach((message) => timeline.append(renderMessage(message)));
        if (!data.messages?.length) renderEmpty();
        status.textContent = data.messages?.length ? `已顯示 ${data.messages.length} 則${visibility === 'public' ? '公開' : '私密'}傳音。` : '此卷正等待第一道回聲。';
        markActivitySeen(ideaSlug, visibility, data.latest_activity_id, data.viewer?.activity_scope || 'anonymous');
      } catch (error) {
        if (error.name === 'AbortError') return;
        timeline.replaceChildren();
        status.textContent = error.message || '目前無法讀取傳音，請稍後再試。';
      } finally {
        timeline.removeAttribute('aria-busy');
      }
    };
    const setVisibility = (nextVisibility) => {
      visibility = nextVisibility;
      tabs.forEach((tab) => {
        const selected = tab.dataset.conversationTab === visibility;
        tab.setAttribute('aria-selected', String(selected));
        tab.tabIndex = selected ? 0 : -1;
      });
      const privateMode = visibility === 'private';
      privacy.querySelector('span').textContent = privateMode ? '封' : '眾';
      privacy.querySelector('strong').textContent = privateMode ? '僅你與守閣者可見' : '所有訪客可閱讀';
      privacyCopy.textContent = privateMode
        ? '私密內容不會進入公開審核區，也不會顯示給其他客戶。'
        : '訪客與已驗證客戶的留言都會先由守閣者審核，再對外公開。';
      loadMessages();
    };
    trigger.addEventListener('click', () => {
      const opening = panel.hidden;
      panel.hidden = !opening;
      trigger.setAttribute('aria-expanded', String(opening));
      triggerLabel.textContent = opening ? '收合對話' : '展開對話';
      widget.classList.toggle('is-open', opening);
      if (opening) {
        if (!loaded) { loaded = true; loadMessages(); }
        panel.focus({preventScroll: true});
      }
    });
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => setVisibility(tab.dataset.conversationTab));
      tab.addEventListener('keydown', (event) => {
        if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
        event.preventDefault();
        const direction = event.key === 'ArrowRight' ? 1 : -1;
        const next = tabs[(index + direction + tabs.length) % tabs.length];
        next.focus();
        setVisibility(next.dataset.conversationTab);
      });
    });
    textarea.addEventListener('input', () => { count.textContent = String(textarea.value.length); });
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const submit = form.querySelector('button[type="submit"]');
      const visitorSubmission = !viewerState.authenticated;
      if (visitorSubmission && !turnstileToken) {
        status.textContent = '請先完成訪客安全確認。';
        ensureTurnstile();
        return;
      }
      submit.disabled = true;
      status.textContent = '正在送出傳音…';
      try {
        const payload = {visibility, body: textarea.value, website: honeypot.value};
        if (ideaSlug) payload.idea_slug = ideaSlug;
        if (visitorSubmission) payload.turnstile_token = turnstileToken;
        const response = await fetch(`/api/conversations/${encodeURIComponent(sectionKey)}/messages`, {
          method: 'POST', credentials: 'same-origin',
          headers: {'Accept': 'application/json', 'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
          body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '傳音未能送出');
        textarea.value = '';
        honeypot.value = '';
        count.textContent = '0';
        await loadMessages();
        status.textContent = visibility === 'public'
          ? '傳音已送達，守閣者審核後會公開；你目前可看見自己的等待狀態。'
          : '私密傳音已送達，只有你與守閣者能看見。';
      } catch (error) {
        status.textContent = error.message || '傳音未能送出，請稍後再試。';
      } finally {
        if (visitorSubmission) resetTurnstile();
        submit.disabled = false;
      }
    });
  });
})();
