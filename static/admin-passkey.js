(() => {
  const publicCsrf = document.querySelector('meta[name="public-csrf"]')?.content || '';
  const adminCsrf = document.querySelector('meta[name="admin-csrf"]')?.content || '';
  const loginStatus = document.querySelector('#passkey-login-status');
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

  const prepareRequestOptions = (options) => ({
    ...options,
    challenge: base64urlToBytes(options.challenge),
    allowCredentials: (options.allowCredentials || []).map((item) => ({
      ...item,
      id: base64urlToBytes(item.id),
    })),
  });

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

  const authenticationPayload = (credential) => ({
    id: credential.id,
    rawId: bytesToBase64url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment,
    response: {
      clientDataJSON: bytesToBase64url(credential.response.clientDataJSON),
      authenticatorData: bytesToBase64url(credential.response.authenticatorData),
      signature: bytesToBase64url(credential.response.signature),
      userHandle: credential.response.userHandle ? bytesToBase64url(credential.response.userHandle) : null,
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

  const passkeyLogin = document.querySelector('#passkey-login');
  passkeyLogin?.addEventListener('click', async () => {
    passkeyLogin.disabled = true;
    setStatus(loginStatus, '正在等待裝置確認…');
    try {
      if (!window.PublicKeyCredential || !navigator.credentials) throw new Error('此瀏覽器不支援 Passkey。');
      const options = await postJson('/admin/passkeys/authentication/options', publicCsrf);
      const credential = await navigator.credentials.get({publicKey: prepareRequestOptions(options.publicKey)});
      if (!credential) throw new Error('未完成 Passkey 驗證。');
      const result = await postJson('/admin/passkeys/authentication/verify', publicCsrf, {
        credential: authenticationPayload(credential),
      });
      setStatus(loginStatus, '驗證成功，正在進入後台…');
      window.location.assign(result.redirect || '/admin');
    } catch (error) {
      const cancelled = error?.name === 'NotAllowedError';
      setStatus(loginStatus, cancelled ? '驗證已取消或逾時，請再試一次。' : (error.message || 'Passkey 驗證失敗。'), true);
      passkeyLogin.disabled = false;
    }
  });

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

  document.querySelectorAll('.passkey-revoke').forEach((button) => {
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
})();
