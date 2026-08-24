(() => {
  const publicCsrf = document.querySelector('meta[name="public-csrf"]')?.content || '';
  const status = document.querySelector('#identity-status');
  const verifyButton = document.querySelector('#identity-verify');

  const setStatus = (message, isError = false) => {
    if (!status) return;
    status.textContent = message;
    status.classList.toggle('is-error', isError);
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

  const prepareRequestOptions = (options) => ({
    ...options,
    challenge: base64urlToBytes(options.challenge),
    allowCredentials: (options.allowCredentials || []).map((item) => ({
      ...item,
      id: base64urlToBytes(item.id),
    })),
  });

  const serializeCredential = (credential) => ({
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

  async function postJson(path, body = null) {
    const options = {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'X-CSRF-Token': publicCsrf},
    };
    if (body !== null) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(body);
    }
    const response = await fetch(path, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || '無法完成身分驗證，請稍後再試。');
    return data;
  }

  verifyButton?.addEventListener('click', async () => {
    verifyButton.disabled = true;
    setStatus('正在等待確認…');
    try {
      if (!window.PublicKeyCredential || !navigator.credentials) {
        throw new Error('目前環境無法完成驗證。');
      }
      const options = await postJson('/admin/identity/options');
      const credential = await navigator.credentials.get({publicKey: prepareRequestOptions(options.publicKey)});
      if (!credential) throw new Error('未完成身分驗證。');
      const result = await postJson('/admin/identity/verify', {
        credential: serializeCredential(credential),
      });
      setStatus('驗證成功，正在進入…');
      window.location.assign(result.redirect || '/admin');
    } catch (error) {
      const cancelled = error?.name === 'NotAllowedError';
      setStatus(
        cancelled ? '驗證已取消或逾時，請再試一次。' : (error.message || '無法完成身分驗證。'),
        true,
      );
      verifyButton.disabled = false;
    }
  });
})();
