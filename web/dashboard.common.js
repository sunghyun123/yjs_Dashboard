(function () {
    function escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    }

    function formatLocalDateYYYYMMDD(d = new Date()) {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${y}-${m}-${day}`;
    }

    function ensureToastElement() {
        let el = document.getElementById('yjsToast');
        if (el) return el;
        el = document.getElementById('saveToast');
        if (el) return el;
        el = document.createElement('div');
        el.id = 'yjsToast';
        el.style.cssText = [
            'position:fixed', 'left:50%', 'bottom:32px',
            'transform:translateX(-50%)', 'background:#212529', 'color:#fff',
            'padding:10px 18px', 'border-radius:24px', 'font-size:0.9rem',
            'z-index:2000', 'box-shadow:0 6px 20px rgba(0,0,0,0.18)',
            'display:none', 'pointer-events:none', 'max-width:90vw',
        ].join(';');
        document.body.appendChild(el);
        return el;
    }

    let toastTimer = null;
    function showSaveToast(message, type = 'info') {
        const el = ensureToastElement();
        el.textContent = String(message || '');
        el.style.display = 'block';
        if (type === 'success') el.style.background = '#1f6f43';
        else if (type === 'error') el.style.background = '#8b1e2b';
        else el.style.background = '#212529';
        if (toastTimer) window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(() => {
            el.style.display = 'none';
            toastTimer = null;
        }, 2200);
    }

    /** alert() 대체. 페이지에서 toast 컨테이너가 있으면 토스트, 없으면 alert로 폴백. */
    function notify(message, type = 'info') {
        try {
            showSaveToast(message, type);
        } catch (_e) {
            window.alert(String(message || ''));
        }
    }

    /** fetch 응답을 안전하게 JSON으로 파싱. 빈 본문/HTML 응답에도 깨지지 않음. */
    async function safeJson(response) {
        try {
            return await response.json();
        } catch (_e) {
            return {};
        }
    }

    window.escapeHtml = escapeHtml;
    window.formatLocalDateYYYYMMDD = formatLocalDateYYYYMMDD;
    window.showSaveToast = showSaveToast;
    window.notify = notify;
    window.safeJson = safeJson;
})();
