(function () {
    function getSidebarState() {
        if (!window.__dashboardSidebarState) {
            window.__dashboardSidebarState = {
                dashboardNotice: '',
            };
        }
        return window.__dashboardSidebarState;
    }

    function loadDashboardNotice() {
        const state = getSidebarState();
        state.dashboardNotice = localStorage.getItem('yjs_dashboard_notice_v1') || '공지: 중요 안내는 관리자에게 문의하세요.';
        renderDashboardNotice();
    }

    function renderDashboardNotice() {
        const state = getSidebarState();
        const el = document.getElementById('dashboardNotice');
        el.textContent = state.dashboardNotice;
        el.title = '클릭하여 공지 수정';
    }

    function beginEditDashboardNotice() {
        const state = getSidebarState();
        const el = document.getElementById('dashboardNotice');
        const current = state.dashboardNotice;
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'form-control form-control-sm';
        input.value = current;
        input.style.maxWidth = '460px';
        const commit = () => {
            state.dashboardNotice = input.value.trim() || '공지: 중요 안내는 관리자에게 문의하세요.';
            localStorage.setItem('yjs_dashboard_notice_v1', state.dashboardNotice);
            renderDashboardNotice();
            bindDashboardNoticeEditor();
        };
        const cancel = () => {
            renderDashboardNotice();
            bindDashboardNoticeEditor();
        };
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') commit();
            if (e.key === 'Escape') cancel();
        });
        input.addEventListener('blur', commit);
        el.replaceWith(input);
        input.id = 'dashboardNotice';
        input.focus();
        input.select();
    }

    function bindDashboardNoticeEditor() {
        const el = document.getElementById('dashboardNotice');
        el.style.cursor = 'pointer';
        el.addEventListener('click', beginEditDashboardNotice, { once: true });
    }

    async function submitBoardTemplate() {
        const catRaw = document.getElementById('boardCategory').value.trim() || '공사 일정';
        const cat = (catRaw === '일정' || catRaw === '일반 작업') ? '일정' : '공사 일정';
        const task = document.getElementById('boardTask').value.trim();
        if (!task) {
            alert('공사명·작업명을 입력하세요.');
            return;
        }
        const rawShift = document.getElementById('boardShiftType').value.trim();
        const shift = (!rawShift && cat === '공사 일정') ? '주간' : rawShift;
        const payload = {
            action_type: 'register',
            date: document.getElementById('boardDate').value.trim() || null,
            task: task,
            person: '',
            details: document.getElementById('boardDetails').value.trim(),
            shift_type: shift,
            work_code: document.getElementById('boardWorkCode').value.trim(),
            category: cat,
            request_note: '',
            schedule_id: null
        };

        const response = await fetch('/api/schedules/board/template-action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) {
            alert(data.detail || '상황판 등록 전송 실패');
            return;
        }
        alert(data.message || '처리 완료');
        loadSchedules();
    }

    function toggleAppDrawer(open) {
        const drawer = document.getElementById('appDrawer');
        const overlay = document.getElementById('appDrawerOverlay');
        const on = Boolean(open);
        drawer.classList.toggle('open', on);
        overlay.classList.toggle('show', on);
        drawer.setAttribute('aria-hidden', on ? 'false' : 'true');
    }

    function toggleDocSubmenu(which) {
        const gen = document.getElementById('docSubmenuGen');
        const ext = document.getElementById('docSubmenuExt');
        if (which === 'gen') {
            gen.classList.toggle('open');
            ext.classList.remove('open');
        } else {
            ext.classList.toggle('open');
            gen.classList.remove('open');
        }
    }

    window.loadDashboardNotice = loadDashboardNotice;
    window.renderDashboardNotice = renderDashboardNotice;
    window.beginEditDashboardNotice = beginEditDashboardNotice;
    window.bindDashboardNoticeEditor = bindDashboardNoticeEditor;
    window.submitBoardTemplate = submitBoardTemplate;
    window.toggleAppDrawer = toggleAppDrawer;
    window.toggleDocSubmenu = toggleDocSubmenu;
})();
