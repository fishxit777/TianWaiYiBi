(() => {
  const adminCsrf = document.querySelector('meta[name="admin-csrf"]')?.content || '';
  const setupStatus = document.querySelector('#passkey-setup-status');

  const setStatus = (target, message, isError = false) => {
    if (!target) return;
    target.textContent = message;
    target.classList.toggle('is-error', isError);
  };

  const base64urlToBytes = (value) => {
    const base64 = String(value).replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
    const decoded = atob(padded);
    return Uint8Array.from(decoded, (character) => character.charCodeAt(0));
  };

  const bytesToBase64url = (value) => {
    const bytes = new Uint8Array(value);
    let binary = '';
    bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
    return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  };

  const prepareCreationOptions = (options) => {
    const prepared = {...options, challenge: base64urlToBytes(options.challenge)};
    prepared.user = {...options.user, id: base64urlToBytes(options.user.id)};
    prepared.excludeCredentials = (options.excludeCredentials || []).map((item) => ({
      ...item,
      id: base64urlToBytes(item.id),
    }));
    return prepared;
  };

  const registrationPayload = (credential) => ({
    id: credential.id,
    rawId: bytesToBase64url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment,
    response: {
      clientDataJSON: bytesToBase64url(credential.response.clientDataJSON),
      attestationObject: bytesToBase64url(credential.response.attestationObject),
      transports: credential.response.getTransports ? credential.response.getTransports() : [],
    },
    clientExtensionResults: credential.getClientExtensionResults(),
  });

  async function postJson(path, csrf, body = null) {
    const options = {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'X-CSRF-Token': csrf},
    };
    if (body !== null) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(body);
    }
    const response = await fetch(path, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || '安全驗證失敗，請重新操作。');
    return data;
  }

  const registerButton = document.querySelector('#passkey-register');
  registerButton?.addEventListener('click', async () => {
    const labelInput = document.querySelector('#passkey-label');
    const label = labelInput?.value.trim() || 'Passkey';
    registerButton.disabled = true;
    setStatus(setupStatus, '正在等待裝置建立 Passkey…');
    try {
      if (!window.PublicKeyCredential || !navigator.credentials) throw new Error('此瀏覽器不支援 Passkey。');
      const options = await postJson('/admin/api/passkeys/registration/options', adminCsrf);
      const credential = await navigator.credentials.create({publicKey: prepareCreationOptions(options.publicKey)});
      if (!credential) throw new Error('未完成 Passkey 建立。');
      const serialized = registrationPayload(credential);
      await postJson('/admin/api/passkeys/registration/verify', adminCsrf, {
        credential: serialized,
        transports: serialized.response.transports,
        label,
      });
      setStatus(setupStatus, 'Passkey 已安全登記。');
      window.location.reload();
    } catch (error) {
      const cancelled = error?.name === 'NotAllowedError';
      setStatus(setupStatus, cancelled ? '建立已取消或逾時，沒有變更任何設定。' : (error.message || 'Passkey 登記失敗。'), true);
      registerButton.disabled = false;
    }
  });

  const activateButton = document.querySelector('#passkey-activate');
  activateButton?.addEventListener('click', async () => {
    if (!window.confirm('啟用後，一般密碼登入會立即停用。請確認兩把 Passkey 都已實際可用。')) return;
    activateButton.disabled = true;
    setStatus(setupStatus, '正在更新登入模式…');
    try {
      await postJson('/admin/api/passkeys/activate', adminCsrf);
      setStatus(setupStatus, 'Passkey 專用模式已啟用。');
      window.location.reload();
    } catch (error) {
      setStatus(setupStatus, error.message || '無法更新登入模式。', true);
      activateButton.disabled = false;
    }
  });

  document.querySelectorAll('.credential-revoke').forEach((button) => {
    button.addEventListener('click', async () => {
      if (!window.confirm('確定撤銷這把 Passkey？撤銷後無法復原。')) return;
      button.disabled = true;
      setStatus(setupStatus, '正在撤銷金鑰…');
      try {
        await postJson(`/admin/api/passkeys/${encodeURIComponent(button.dataset.credentialId)}/revoke`, adminCsrf);
        setStatus(setupStatus, 'Passkey 已撤銷。');
        window.location.reload();
      } catch (error) {
        setStatus(setupStatus, error.message || '無法撤銷 Passkey。', true);
        button.disabled = false;
      }
    });
  });

  const recoveryCodeButton = document.querySelector('#recovery-code-generate');
  let recoveryCodes = [];
  recoveryCodeButton?.addEventListener('click', async () => {
    const replacing = recoveryCodeButton.textContent.includes('重新');
    if (replacing && !window.confirm('重新產生後，尚未使用的舊復原碼會全部失效。確定繼續？')) return;
    recoveryCodeButton.disabled = true;
    setStatus(setupStatus, '正在產生復原碼…');
    try {
      const result = await postJson('/admin/api/passkeys/recovery-codes', adminCsrf);
      recoveryCodes = result.codes || [];
      const list = document.querySelector('#recovery-code-list');
      list.replaceChildren(...recoveryCodes.map((code) => {
        const item = document.createElement('li');
        item.textContent = code;
        return item;
      }));
      document.querySelector('#recovery-code-output').hidden = false;
      setStatus(setupStatus, '復原碼已產生；請立即安全保存。');
      recoveryCodeButton.textContent = '重新產生並撤銷目前代碼';
      recoveryCodeButton.disabled = false;
    } catch (error) {
      setStatus(setupStatus, error.message || '無法產生復原碼。', true);
      recoveryCodeButton.disabled = false;
    }
  });

  document.querySelector('#recovery-code-download')?.addEventListener('click', () => {
    if (!recoveryCodes.length) return;
    const header = '天外一筆管理員一次性緊急復原碼\n每組僅可使用一次；請離線加密保存。\n\n';
    const blob = new Blob([header + recoveryCodes.join('\n') + '\n'], {type: 'text/plain;charset=utf-8'});
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'tianwai-yibi-recovery-codes.txt';
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 0);
  });
})();
