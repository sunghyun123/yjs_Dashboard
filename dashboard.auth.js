(function () {
    function consumeKakaoUrlMessage() {
        try {
            const u = new URL(window.location.href);
            if (!u.searchParams.has('kakao_denied') && !u.searchParams.has('kakao_error')) return '';
            let msg = '';
            if (u.searchParams.get('kakao_denied') === 'whitelist') {
                msg =
                    '허용 목록에 없는 카카오 계정입니다. 저장소의 kakao_whitelist.json에 본인 카카오 사용자 ID를 추가한 뒤 다시 시도하세요.';
            } else {
                const e = u.searchParams.get('kakao_error');
                if (e) msg = decodeURIComponent(e.replace(/\+/g, ' '));
            }
            u.searchParams.delete('kakao_denied');
            u.searchParams.delete('kakao_error');
            const qs = u.searchParams.toString();
            window.history.replaceState({}, '', u.pathname + (qs ? '?' + qs : '') + u.hash);
            return msg;
        } catch (_e) {
            return '';
        }
    }

    function showDashboardLoginError(message) {
        const el = document.getElementById('dashboardLoginError');
        const msg = String(message || '').trim();
        if (!msg) {
            el.style.display = 'none';
            el.textContent = '';
            return;
        }
        el.style.display = 'block';
        el.textContent = msg;
    }

    function openDashboardLoginModal(message) {
        const urlMsg = consumeKakaoUrlMessage();
        const combined = String(message || '').trim() || urlMsg;
        showDashboardLoginError(combined);
        window.dashboardLoginModal.show();
    }

    function startKakaoLogin() {
        const path = window.location.pathname || '/dashboard.html';
        const next = encodeURIComponent(path);
        window.location.href = '/api/auth/kakao/login?next=' + next;
    }

    async function ensureSession() {
        const urlMsg = consumeKakaoUrlMessage();
        try {
            const response = await fetch('/api/auth/me');
            if (!response.ok) {
                showDashboardLoginError(urlMsg);
                window.dashboardLoginModal.show();
                return false;
            }
            const me = await response.json();
            const drawerAdmin = document.getElementById('drawerAdminLink');
            if (me.role === 'admin') drawerAdmin.classList.remove('d-none');
            else drawerAdmin.classList.add('d-none');
            window.dashboardLoginModal.hide();
            showDashboardLoginError('');
            return true;
        } catch (e) {
            showDashboardLoginError(urlMsg || '로그인 상태를 확인하지 못했습니다. 네트워크를 확인해 주세요.');
            window.dashboardLoginModal.show();
            return false;
        }
    }

    async function logout() {
        await fetch('/api/auth/logout', { method: 'POST' });
        openDashboardLoginModal('로그아웃되었습니다. 다시 로그인해 주세요.');
    }

    async function reopenDashboardLoginIfLoggedOut() {
        try {
            const res = await fetch('/api/auth/me');
            if (!res.ok) openDashboardLoginModal('');
        } catch (_e) {
            openDashboardLoginModal('로그인 상태를 확인하지 못했습니다. 네트워크를 확인해 주세요.');
        }
    }

    window.showDashboardLoginError = showDashboardLoginError;
    window.openDashboardLoginModal = openDashboardLoginModal;
    window.ensureSession = ensureSession;
    window.logout = logout;
    window.startKakaoLogin = startKakaoLogin;
    window.reopenDashboardLoginIfLoggedOut = reopenDashboardLoginIfLoggedOut;
})();
