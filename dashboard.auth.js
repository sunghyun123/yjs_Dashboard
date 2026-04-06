(function () {
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

    function openDashboardLoginModal(message = '') {
        showDashboardLoginError(message);
        const userInput = document.getElementById('dashboardLoginUserId');
        const pwInput = document.getElementById('dashboardLoginPassword');
        pwInput.value = '';
        if (String(userInput.value || '').trim()) pwInput.focus();
        else userInput.focus();
        window.dashboardLoginModal.show();
    }

    async function ensureSession() {
        try {
            const response = await fetch('/api/auth/me');
            if (!response.ok) {
                openDashboardLoginModal('');
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
            openDashboardLoginModal('로그인 상태를 확인하지 못했습니다. 네트워크를 확인해 주세요.');
            return false;
        }
    }

    async function logout() {
        await fetch('/api/auth/logout', { method: 'POST' });
        openDashboardLoginModal('로그아웃되었습니다. 다시 로그인해 주세요.');
    }

    async function submitDashboardLogin() {
        const userId = String(document.getElementById('dashboardLoginUserId').value || '').trim();
        const password = String(document.getElementById('dashboardLoginPassword').value || '').trim();
        if (!userId || !password) {
            showDashboardLoginError('아이디와 비밀번호를 모두 입력해 주세요.');
            return;
        }
        try {
            const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: userId,
                    password,
                    register_code: '',
                    device_name: navigator.userAgent || 'dashboard-browser'
                })
            });
            const data = await res.json();
            if (!res.ok) {
                showDashboardLoginError(data.detail || '로그인에 실패했습니다.');
                return;
            }
            showDashboardLoginError('');
            await initializeDashboardPage();
        } catch (e) {
            showDashboardLoginError('로그인 요청 중 오류가 발생했습니다.');
        }
    }

    function openDashboardSignupFromLogin() {
        window.dashboardLoginModal.hide();
        window.dashboardSignupModal.show();
    }

    function openDashboardFindAccountFromLogin() {
        document.getElementById('dashFindAccountResult').textContent = '';
        window.dashboardLoginModal.hide();
        window.dashboardFindAccountModal.show();
    }

    async function reopenDashboardLoginIfLoggedOut() {
        try {
            const res = await fetch('/api/auth/me');
            if (!res.ok) openDashboardLoginModal('');
        } catch (_e) {
            openDashboardLoginModal('로그인 상태를 확인하지 못했습니다. 네트워크를 확인해 주세요.');
        }
    }

    async function submitDashboardSignup() {
        const payload = {
            user_name: document.getElementById('dashSignupUserName').value.trim(),
            user_id: document.getElementById('dashSignupUserId').value.trim(),
            password: document.getElementById('dashSignupPassword').value
        };
        try {
            const res = await fetch('/api/auth/signup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (!res.ok) {
                alert(data.detail || '가입에 실패했습니다.');
                return;
            }
            alert('가입신청이 완료되었습니다. 이제 등록한 ID/비밀번호로 로그인할 수 있습니다.');
            window.dashboardSignupModal.hide();
            document.getElementById('dashSignupUserName').value = '';
            document.getElementById('dashSignupUserId').value = '';
            document.getElementById('dashSignupPassword').value = '';
        } catch (e) {
            alert('가입 처리 중 통신 오류가 발생했습니다.');
        }
    }

    async function submitDashboardFindAccount() {
        const userName = document.getElementById('dashFindUserName').value.trim();
        const userIdInput = document.getElementById('dashFindUserId');
        const resultBox = document.getElementById('dashFindAccountResult');
        if (!userName) {
            resultBox.textContent = '이름을 입력해 주세요.';
            return;
        }
        try {
            const res = await fetch('/api/auth/find-account', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_name: userName })
            });
            const data = await res.json();
            if (!res.ok) {
                resultBox.textContent = data.detail || '등록된 계정 정보가 없습니다.';
                return;
            }
            userIdInput.value = data.user_id || '';
            resultBox.innerHTML = `ID: <strong>${data.user_id}</strong><br>${data.message || '비밀번호는 조회되지 않습니다.'}`;
        } catch (e) {
            resultBox.textContent = '계정 조회 중 통신 오류가 발생했습니다.';
        }
    }

    async function submitDashboardResetPassword() {
        const userName = document.getElementById('dashFindUserName').value.trim();
        const userId = document.getElementById('dashFindUserId').value.trim();
        const newPassword = document.getElementById('dashResetNewPassword').value;
        const resultBox = document.getElementById('dashFindAccountResult');
        if (!userName || !userId || !newPassword) {
            resultBox.textContent = '이름, 계정 ID, 새 비밀번호를 모두 입력해 주세요.';
            return;
        }
        try {
            const res = await fetch('/api/auth/reset-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_name: userName, user_id: userId, new_password: newPassword })
            });
            const data = await res.json();
            if (!res.ok) {
                resultBox.textContent = data.detail || '비밀번호 재설정에 실패했습니다.';
                return;
            }
            resultBox.textContent = data.message || '비밀번호가 재설정되었습니다.';
            document.getElementById('dashResetNewPassword').value = '';
        } catch (e) {
            resultBox.textContent = '비밀번호 재설정 중 통신 오류가 발생했습니다.';
        }
    }

    window.showDashboardLoginError = showDashboardLoginError;
    window.openDashboardLoginModal = openDashboardLoginModal;
    window.ensureSession = ensureSession;
    window.logout = logout;
    window.submitDashboardLogin = submitDashboardLogin;
    window.openDashboardSignupFromLogin = openDashboardSignupFromLogin;
    window.openDashboardFindAccountFromLogin = openDashboardFindAccountFromLogin;
    window.reopenDashboardLoginIfLoggedOut = reopenDashboardLoginIfLoggedOut;
    window.submitDashboardSignup = submitDashboardSignup;
    window.submitDashboardFindAccount = submitDashboardFindAccount;
    window.submitDashboardResetPassword = submitDashboardResetPassword;
})();
