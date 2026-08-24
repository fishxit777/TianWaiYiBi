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
    const formLabel = form.querySelector('[data-conversation-form-label]');
    const count = form.querySelector('[data-conversation-count]');
    const loginNote = widget.querySelector('[data-conversation-login-note]');
    const viewerKey = widget.querySelector('[data-conversation-viewer-key]');
    const sectionKey = widget.dataset.sectionKey;
    const ideaSlug = widget.dataset.ideaSlug || '';
    let visibility = 'public';
    let loaded = false;
    let controller = null;

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
      empty.append(
        element('span', '', visibility === 'public' ? '◇' : '封'),
        element('strong', '', visibility === 'public' ? '此卷尚無公開傳音' : '這裡還沒有私密對話'),
        element('p', '', visibility === 'public' ? '若你已是客戶，可以留下第一道回聲。' : '只有你與守閣者能看見這裡的內容。')
      );
      timeline.append(empty);
    };
    const updateViewer = (viewer) => {
      const authenticated = Boolean(viewer?.authenticated);
      form.hidden = !authenticated;
      loginNote.hidden = authenticated;
      if (authenticated) {
        viewerKey.hidden = false;
        applyIdentity(viewerKey, viewer.color);
        viewerKey.querySelector('b').textContent = `${viewer.alias}（你）`;
      } else {
        viewerKey.hidden = true;
      }
      formLabel.textContent = visibility === 'public' ? '留下公開傳音' : '只給守閣者的私密傳音';
      textarea.placeholder = visibility === 'public'
        ? '寫下你的想法或疑問；公開傳音請勿放入個人資料或網址。'
        : '只有你與守閣者能看見；仍請勿輸入密碼、驗證碼或付款資料。';
    };
    const showLoginRequired = () => {
      timeline.replaceChildren();
      const empty = element('div', 'conversation-empty conversation-empty-private');
      empty.append(element('span', '', '封'), element('strong', '', '登入後開啟私密傳音'), element('p', '', '此處不會向其他訪客顯示，也不使用顏色代替權限。'));
      timeline.append(empty);
      form.hidden = true;
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
      privacyCopy.textContent = privateMode ? '私密內容不會進入公開審核區，也不會顯示給其他客戶。' : '已驗證客戶的留言會先由守閣者審核，再對外公開。';
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
      submit.disabled = true;
      status.textContent = '正在送出傳音…';
      try {
        const payload = {visibility, body: textarea.value};
        if (ideaSlug) payload.idea_slug = ideaSlug;
        const response = await fetch(`/api/conversations/${encodeURIComponent(sectionKey)}/messages`, {
          method: 'POST', credentials: 'same-origin',
          headers: {'Accept': 'application/json', 'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
          body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '傳音未能送出');
        textarea.value = '';
        count.textContent = '0';
        await loadMessages();
        status.textContent = visibility === 'public'
          ? '傳音已送達，守閣者審核後會公開；你目前可看見自己的等待狀態。'
          : '私密傳音已送達，只有你與守閣者能看見。';
      } catch (error) {
        status.textContent = error.message || '傳音未能送出，請稍後再試。';
      } finally {
        submit.disabled = false;
      }
    });
  });
})();
