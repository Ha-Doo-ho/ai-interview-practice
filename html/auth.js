/* Existing cookie-based authentication; no credentials or tokens in browser storage. */
(function () {
  'use strict';
  const state = {user: null, status: 'checking', busy: false, mode: 'login'};
  const byId = id => document.getElementById(id);
  let api;
  const listeners = new Set();
  const sessionState = () => ({status: state.status, user: state.user ? {...state.user} : null});
  window.AstraAuth = {
    subscribe(listener) { listeners.add(listener); listener(sessionState()); return () => listeners.delete(listener); },
    recheck: restoreSession,
  };

  function message(id, text = '') {
    byId(id).textContent = text;
    byId(id).hidden = !text;
  }

  function clearPasswords() {
    byId('auth-password').value = '';
    byId('auth-confirm').value = '';
  }

  function checkedUser(value) {
    if (!value || typeof value.user_id !== 'string' || !value.user_id ||
        typeof value.username !== 'string' || !value.username) throw Error('unreadable_response');
    return {user_id: value.user_id, username: value.username};
  }

  function render() {
    for (const listener of listeners) listener(sessionState());
    const signedIn = state.status === 'authenticated';
    const guest = state.status === 'guest';
    byId('auth-status').textContent = signedIn ? `${state.user.username}님 · 로그인됨` :
      state.status === 'checking' ? '로그인 상태를 확인하고 있습니다.' :
      guest ? '로그인하지 않은 상태입니다.' : '로그인 상태를 확인하지 못했습니다.';
    byId('auth-open-login').hidden = !guest;
    byId('auth-open-register').hidden = !guest;
    byId('auth-logout').hidden = !signedIn;
    byId('auth-retry').hidden = state.status !== 'unknown';
    for (const id of ['auth-open-login', 'auth-open-register', 'auth-logout', 'auth-retry', 'auth-close', 'auth-mode-login', 'auth-mode-register']) {
      byId(id).disabled = state.busy;
    }
    for (const id of ['auth-username', 'auth-password', 'auth-confirm', 'auth-submit']) {
      byId(id).disabled = state.busy || !guest;
    }
    byId('auth-form').setAttribute('aria-busy', String(state.busy));
    byId('auth-submit').textContent = state.busy ? '처리 중입니다…' : state.mode === 'register' ? '회원가입하고 로그인' : '로그인';
    for (const mode of ['login', 'register']) {
      byId('auth-open-' + mode).setAttribute('aria-expanded', String(!byId('auth-panel').hidden && state.mode === mode));
      byId('auth-mode-' + mode).setAttribute('aria-pressed', String(state.mode === mode));
    }
  }

  function hidePanel() {
    clearPasswords();
    byId('auth-panel').hidden = true;
    message('auth-form-error');
  }

  function acceptUser(user) {
    state.user = checkedUser(user);
    state.status = 'authenticated';
    byId('auth-username').value = '';
    hidePanel();
  }

  function openPanel(mode) {
    if (state.busy || state.status !== 'guest') return;
    state.mode = mode;
    clearPasswords();
    message('auth-form-error');
    message('auth-session-error');
    byId('auth-title').textContent = mode === 'register' ? '회원가입' : '로그인';
    byId('auth-confirm-field').hidden = mode !== 'register';
    byId('auth-confirm').required = mode === 'register';
    byId('auth-password').autocomplete = mode === 'register' ? 'new-password' : 'current-password';
    byId('auth-panel').hidden = false;
    render();
    byId('auth-username').focus();
  }

  async function restoreSession() {
    if (state.busy) return;
    state.busy = true;
    state.status = 'checking';
    message('auth-session-error');
    render();
    try {
      acceptUser(await api('/me'));
    } catch (error) {
      state.user = null;
      state.status = error.status === 401 ? 'guest' : 'unknown';
      if (state.status === 'unknown') message('auth-session-error', '서버에 연결해 로그인 상태를 확인하지 못했습니다. 연결을 확인한 뒤 다시 확인해 주세요.');
    } finally {
      state.busy = false;
      render();
    }
  }

  async function submit(event) {
    event.preventDefault();
    if (state.busy || state.status !== 'guest') return;
    const username = byId('auth-username').value.trim();
    const password = byId('auth-password').value;
    message('auth-form-error');
    if (Array.from(username).length < 2 || Array.from(username).length > 64 || Array.from(password).length < 8) {
      message('auth-form-error', '아이디는 2~64자, 비밀번호는 8자 이상으로 입력해 주세요.');
      byId('auth-form-error').focus();
      return;
    }
    if (state.mode === 'register' && password !== byId('auth-confirm').value) {
      message('auth-form-error', '비밀번호와 비밀번호 확인이 일치하지 않습니다.');
      byId('auth-confirm').focus();
      return;
    }
    state.busy = true;
    message('auth-session-error');
    render();
    try {
      acceptUser(await api('/' + state.mode, {method: 'POST', body: {username, password}}));
    } catch (error) {
      // The request may have succeeded despite a lost response. Never blindly repeat registration.
      if (!error.status || error.status >= 500) {
        try {
          const current = checkedUser(await api('/me'));
          acceptUser(current);
          if (current.username !== username) message('auth-session-error', '서버에 로그인된 계정을 확인했습니다. 상단의 아이디를 확인해 주세요.');
        } catch (checkError) {
          state.user = null;
          state.status = checkError.status === 401 ? 'guest' : 'unknown';
          const notice = state.mode === 'register'
            ? '가입 결과를 확인하지 못했습니다. 이미 계정이 만들어졌을 수 있으니 연결을 확인한 뒤 로그인해 주세요.'
            : '로그인 결과를 확인하지 못했습니다. 연결을 확인한 뒤 다시 시도해 주세요.';
          message(state.status === 'unknown' ? 'auth-session-error' : 'auth-form-error', notice);
        }
      } else {
        const messages = {
          invalid_credentials: '아이디 또는 비밀번호가 올바르지 않습니다.',
          username_taken: '이미 사용 중인 아이디입니다. 다른 아이디를 사용하거나 로그인해 주세요.',
          validation_error: '아이디는 2~64자, 비밀번호는 8자 이상으로 입력해 주세요.'
        };
        message('auth-form-error', messages[error.code] || '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.');
      }
    } finally {
      clearPasswords();
      state.busy = false;
      render();
      if (!byId('auth-form-error').hidden) byId('auth-form-error').focus();
    }
  }

  function completeLogout() {
    state.user = null;
    state.status = 'guest';
    hidePanel();
    byId('auth-username').value = '';
    // Clear ephemeral interview text before reloading the unsaved preview.
    for (const input of document.querySelectorAll('textarea')) input.value = '';
    window.location.reload();
  }

  async function logout() {
    if (state.busy || state.status !== 'authenticated') return;
    state.busy = true;
    message('auth-session-error');
    render();
    try {
      await api('/logout', {method: 'POST'});
      completeLogout();
    } catch (_) {
      try {
        acceptUser(await api('/me'));
        message('auth-session-error', '로그아웃을 완료하지 못했습니다. 다시 시도해 주세요.');
      } catch (error) {
        if (error.status === 401) completeLogout();
        else {
          state.user = null;
          state.status = 'unknown';
          message('auth-session-error', '로그아웃 결과를 확인하지 못했습니다. 연결을 확인한 뒤 로그인 상태를 다시 확인해 주세요.');
        }
      }
    } finally {
      state.busy = false;
      render();
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    api = window.AstraClient.createApi();
    for (const mode of ['login', 'register']) {
      byId('auth-open-' + mode).addEventListener('click', () => openPanel(mode));
      byId('auth-mode-' + mode).addEventListener('click', () => openPanel(mode));
    }
    const close = () => {
      if (state.busy) return;
      hidePanel(); render(); byId('auth-open-' + state.mode).focus();
    };
    byId('auth-close').addEventListener('click', close);
    byId('auth-panel').addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
    byId('auth-form').addEventListener('submit', submit);
    byId('auth-retry').addEventListener('click', restoreSession);
    byId('auth-logout').addEventListener('click', logout);
    window.addEventListener('pageshow', event => { if (event.persisted) restoreSession(); });
    return restoreSession();
  });
})();
