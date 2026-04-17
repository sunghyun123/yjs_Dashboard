(function () {
    const SAMPLE_PROJECT_PROGRESS = [
        { name: '안양 소호타운 리모델링', percent: 91, manager: '현장소장 김대리', phase: '마감 공정' },
        { name: '의왕 물류센터 전기증설', percent: 64, manager: '현장소장 이과장', phase: '중간 점검' },
        { name: '수원 지식산업센터 증축', percent: 47, manager: '현장소장 박팀장', phase: '골조 진행' },
        { name: '화성 공장 신축', percent: 28, manager: '현장소장 정차장', phase: '기초 공정' },
        { name: '평택 사무동 인테리어', percent: 76, manager: '현장소장 송주임', phase: '마감 준비' },
    ];

    const SALES_PROFIT_SAMPLE = {
        labels: ['1월', '2월', '3월', '4월', '5월', '6월', '7월', '8월', '9월', '10월', '11월', '12월'],
        profit: [175000000, 271000000, -24000000, 18000000, 5000000, 7000000, 12000000, 9000000, 4000000, 3000000, 8000000, 14000000],
        input: [142000000, 306000000, 153000000, 28000000, 6000000, 9000000, 15000000, 11000000, 7000000, 4000000, 9000000, 12000000],
        outcome: [312000000, 578000000, 140000000, 46000000, 11000000, 16000000, 27000000, 20000000, 11000000, 7000000, 17000000, 26000000],
    };

    let salesProfitChart = null;
    let projectProgressCarousel = null;
    let workerReturnTimeModal = null;
    let workerReturnTimeTargetUser = '';

    function formatLocalDateYYYYMMDD(d = new Date()) {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${y}-${m}-${day}`;
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    }

    function normalizeShiftType(raw) {
        const val = String(raw || '').trim();
        if (val === '주간') return '주간';
        if (val === '야간' || val === '심야') return '야간';
        return '';
    }

    function statusLabelText(status) {
        if (status === '야간작업') return '야간 작업';
        return status || '사무실';
    }

    function statusBadgeClass(status) {
        if (status === '외출') return 'bg-warning text-dark';
        if (status === '야간작업') return 'bg-danger';
        if (status === '휴가') return 'bg-secondary';
        return 'bg-success';
    }

    function nextStatus(current) {
        if (current === '사무실') return '외출';
        if (current === '외출') return '야간작업';
        if (current === '야간작업') return '휴가';
        return '사무실';
    }

    function parseTimeText(value) {
        const raw = String(value || '').trim();
        if (!raw) return '';
        const m = raw.match(/^(\d{2}):(\d{2})$/);
        if (!m) return '';
        const hh = Number(m[1]);
        const mm = Number(m[2]);
        if (Number.isNaN(hh) || Number.isNaN(mm) || hh < 0 || hh > 23 || (mm !== 0 && mm !== 30)) return '';
        return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`;
    }

    function halfHourIndexToTimeText(index) {
        const safe = Math.max(0, Math.min(47, Number(index) || 0));
        const hh = Math.floor(safe / 2);
        const mm = safe % 2 === 0 ? 0 : 30;
        return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`;
    }

    function timeTextToHalfHourIndex(value) {
        const normalized = parseTimeText(value);
        if (!normalized) return 18;
        const [hhText, mmText] = normalized.split(':');
        const hh = Number(hhText);
        const mm = Number(mmText);
        return hh * 2 + (mm === 30 ? 1 : 0);
    }

    function formatReturnTime(untilTime) {
        const raw = String(untilTime || '').trim();
        if (!raw) return '';
        const normalized = raw.replace(' ', 'T');
        const dt = new Date(normalized);
        if (!Number.isNaN(dt.getTime())) {
            const hh = String(dt.getHours()).padStart(2, '0');
            const mm = String(dt.getMinutes()).padStart(2, '0');
            return `${hh}:${mm}`;
        }
        const matched = raw.match(/(\d{2}):(\d{2})/);
        return matched ? `${matched[1]}:${matched[2]}` : raw;
    }

    function updateNowLabel() {
        const days = ['일', '월', '화', '수', '목', '금', '토'];
        const now = new Date();
        const text = `${now.getFullYear()}.${String(now.getMonth() + 1).padStart(2, '0')}.${String(now.getDate()).padStart(2, '0')} (${days[now.getDay()]})`;
        const el = document.getElementById('homeNowLabel');
        if (el) el.textContent = text;
    }

    function toSafeExternalUrl(rawUrl) {
        const raw = String(rawUrl || '').trim();
        if (!raw) return '#';
        if (/^https?:\/\//i.test(raw)) return raw;
        return `https://${raw}`;
    }

    function buildFaviconUrl(rawUrl) {
        try {
            const safeUrl = toSafeExternalUrl(rawUrl || '');
            const parsed = new URL(safeUrl);
            const host = parsed.hostname;
            if (!host) return '';
            return `https://www.google.com/s2/favicons?sz=64&domain=${encodeURIComponent(host)}`;
        } catch (_e) {
            return '';
        }
    }

    function chunkArray(source, size) {
        const chunkSize = Math.max(1, Number(size) || 1);
        const chunks = [];
        for (let idx = 0; idx < source.length; idx += chunkSize) {
            chunks.push(source.slice(idx, idx + chunkSize));
        }
        return chunks;
    }

    function renderProjectProgressHome() {
        const inner = document.getElementById('projectProgressCarouselInner');
        const indicators = document.getElementById('projectProgressCarouselIndicators');
        if (!inner || !indicators) return;
        const carouselRoot = document.getElementById('projectProgressCarousel');
        if (!carouselRoot) return;

        const perSlide = 3;
        const pages = chunkArray(SAMPLE_PROJECT_PROGRESS, perSlide);

        inner.innerHTML = pages.map((group, pageIdx) => `
            <div class="carousel-item ${pageIdx === 0 ? 'active' : ''}">
                <div class="progress-slide-stack">
                    ${Array.from({ length: perSlide }).map((_, cardIdx) => {
                        const item = group[cardIdx] || null;
                        if (!item) {
                            return '<div class="progress-slide-card is-placeholder" aria-hidden="true"></div>';
                        }
                        const percent = Math.max(0, Math.min(100, Number(item.percent) || 0));
                        return `
                        <div class="progress-slide-card">
                            <div class="d-flex justify-content-between align-items-center gap-2">
                                <div class="progress-project" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</div>
                                <div class="progress-percent">${percent}%</div>
                            </div>
                            <div class="progress mt-2" role="progressbar" aria-label="공정률 ${percent}%">
                                <div class="progress-bar bg-success" style="width:${percent}%"></div>
                            </div>
                            <div class="progress-meta mt-1" title="${escapeHtml(item.phase)} · ${escapeHtml(item.manager)}">${escapeHtml(item.phase)} · ${escapeHtml(item.manager)}</div>
                        </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `).join('');

        indicators.innerHTML = pages.map((_, idx) => `
            <button type="button"
                data-bs-target="#projectProgressCarousel"
                data-bs-slide-to="${idx}"
                class="${idx === 0 ? 'active' : ''}"
                ${idx === 0 ? 'aria-current="true"' : ''}
                aria-label="슬라이드 ${idx + 1}"></button>
        `).join('');

        if (projectProgressCarousel) {
            projectProgressCarousel.dispose();
        }
        projectProgressCarousel = new bootstrap.Carousel(carouselRoot, {
            interval: 5000,
            pause: 'hover',
            ride: 'carousel',
            touch: true,
            wrap: true,
        });
    }

    function renderSalesProfitChartHome() {
        const chartEl = document.getElementById('salesProfitChart');
        if (!chartEl || typeof Chart === 'undefined') return;
        const ctx = chartEl.getContext('2d');
        if (!ctx) return;
        if (salesProfitChart) salesProfitChart.destroy();

        salesProfitChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: SALES_PROFIT_SAMPLE.labels,
                datasets: [
                    {
                        label: '손익금액',
                        data: SALES_PROFIT_SAMPLE.profit,
                        backgroundColor: 'rgba(222, 102, 43, 0.85)',
                        borderColor: 'rgba(191, 78, 25, 1)',
                        borderWidth: 1,
                    },
                    {
                        label: '투입금액',
                        data: SALES_PROFIT_SAMPLE.input,
                        backgroundColor: 'rgba(119, 177, 67, 0.85)',
                        borderColor: 'rgba(95, 149, 48, 1)',
                        borderWidth: 1,
                    },
                    {
                        label: '성과금액',
                        data: SALES_PROFIT_SAMPLE.outcome,
                        backgroundColor: 'rgba(233, 179, 52, 0.85)',
                        borderColor: 'rgba(197, 147, 29, 1)',
                        borderWidth: 1,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { position: 'right' },
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback(value) {
                                return Number(value).toLocaleString('ko-KR');
                            },
                        },
                    },
                },
            },
        });
    }

    function renderShortcutGridHome(rows) {
        const box = document.getElementById('homeFrequentSiteList');
        if (!box) return;

        if (!rows || rows.length === 0) {
            box.innerHTML = '<div class="text-muted small">등록된 바로가기가 없습니다. 관리자 페이지의「홈 화면 바로가기 사이트 관리」에서 추가하면 여기에 표시됩니다.</div>';
            return;
        }

        box.innerHTML = rows.map((row) => {
            const safeUrl = toSafeExternalUrl(row.url || '#');
            const fallbackIcon = escapeHtml(row.icon || '🔗');
            const faviconUrl = buildFaviconUrl(safeUrl);
            const hasFavicon = Boolean(faviconUrl);
            return `
            <a class="mini-link" href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer">
                ${hasFavicon
                    ? `<img class="mini-link-favicon" src="${escapeHtml(faviconUrl)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
                    : ''
                }
                <span class="mini-link-icon-fallback${hasFavicon ? ' d-none' : ''}">${fallbackIcon}</span>
                <span>${escapeHtml(row.title || '이름 없음')}</span>
            </a>
        `;
        }).join('');

        box.querySelectorAll('.mini-link').forEach((linkEl) => {
            const imgEl = linkEl.querySelector('.mini-link-favicon');
            const fallbackEl = linkEl.querySelector('.mini-link-icon-fallback');
            if (!imgEl || !fallbackEl) return;
            imgEl.addEventListener('error', () => {
                imgEl.classList.add('d-none');
                fallbackEl.classList.remove('d-none');
            });
            imgEl.addEventListener('load', () => {
                imgEl.classList.remove('d-none');
                fallbackEl.classList.add('d-none');
            });
        });
    }

    async function fetchMeAndPaint() {
        try {
            const res = await fetch('/api/auth/me');
            if (!res.ok) return;
            const me = await res.json();
            const badge = document.getElementById('homeUserBadge');
            if (badge && me.user_id) {
                badge.textContent = me.user_id;
                badge.classList.remove('d-none');
            }
        } catch (_e) {
            // noop
        }
    }

    async function loadOverview() {
        const today = formatLocalDateYYYYMMDD();
        try {
            const [scheduleRes, statusRes] = await Promise.all([
                fetch(`/api/schedules/today?date=${encodeURIComponent(today)}`),
                fetch('/api/schedules/worker-status'),
            ]);
            const scheduleJson = await scheduleRes.json().catch(() => ({}));
            const statusJson = await statusRes.json().catch(() => ({}));

            const schedules = Array.isArray(scheduleJson.data) ? scheduleJson.data : [];
            const statuses = Array.isArray(statusJson.data) ? statusJson.data : [];

            const nightCount = schedules.filter((row) => normalizeShiftType(row.shift_type || '') === '야간').length;
            const outingCount = statuses.filter((row) => String(row.status || '') === '외출').length;

            document.getElementById('kpiTodaySchedules').textContent = String(schedules.length);
            document.getElementById('kpiNightSchedules').textContent = String(nightCount);
            document.getElementById('kpiOutingStaff').textContent = String(outingCount);
        } catch (_e) {
            // noop
        }
    }

    async function saveWorkerStatusPatch(userName, patch) {
        const currentRowsRes = await fetch('/api/schedules/worker-status');
        const currentRowsJson = await currentRowsRes.json();
        const rows = currentRowsJson.data || [];
        const row = rows.find((r) => String(r.user_name) === String(userName)) || {
            user_name: userName,
            status: '사무실',
            location: '',
            until_time: '',
            note: '',
        };
        const payload = {
            user_name: userName,
            status: patch.status ?? row.status ?? '사무실',
            location: patch.location ?? row.location ?? '',
            until_time: patch.until_time ?? row.until_time ?? '',
            note: '',
        };
        const response = await fetch('/api/schedules/worker-status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
            alert(data.detail || '상태 저장 실패');
            return false;
        }
        return true;
    }

    async function loadWorkerStatusHome() {
        const list = document.getElementById('workerStatusListHome');
        try {
            const [statusRes, outingRes] = await Promise.all([
                fetch('/api/schedules/worker-status'),
                fetch('/api/schedules/outing-staff'),
            ]);
            const data = await statusRes.json();
            const outingData = await outingRes.json();
            if (!statusRes.ok || !outingRes.ok) {
                list.innerHTML = '<div class="text-danger small">상태 조회 실패</div>';
                return;
            }
            const statusMap = new Map((data.data || []).map((r) => [String(r.user_name), r]));
            const outingStaff = outingData.data || [];
            if (!outingStaff.length) {
                list.innerHTML = '<div class="text-muted small">등록된 인원이 없습니다.</div>';
                return;
            }
            list.innerHTML = outingStaff.map((staff) => {
                const row = statusMap.get(String(staff.name)) || {
                    user_name: staff.name,
                    status: '사무실',
                    location: '',
                    until_time: '',
                };
                const locationLabel = row.location ? `행선: ${escapeHtml(row.location)}` : '행선 입력';
                const returnLabel = row.until_time ? `복귀 ${escapeHtml(formatReturnTime(row.until_time))}` : '복귀 미정';
                const isOuting = String(row.status || '') === '외출';
                const outingMetaHtml = isOuting
                    ? `
                            <button type="button" class="btn btn-link btn-sm p-0 text-decoration-none"
                                onclick="handleWorkerLocationClickHome('${encodeURIComponent(row.user_name)}','${encodeURIComponent(row.location || '')}')">${locationLabel}</button>
                            <button type="button" class="btn btn-link btn-sm p-0 text-decoration-none"
                                onclick="handleWorkerUntilClickHome('${encodeURIComponent(row.user_name)}','${encodeURIComponent(row.until_time || '')}')">${returnLabel}</button>
                    `
                    : '';
                return `
                    <div class="worker-row">
                        <div class="d-flex justify-content-between align-items-center gap-2">
                            <b class="text-truncate">${escapeHtml(row.user_name)}</b>
                            <button type="button" class="btn btn-sm badge ${statusBadgeClass(row.status)}"
                                onclick="handleWorkerStatusClickHome('${encodeURIComponent(row.user_name)}','${encodeURIComponent(row.status || '사무실')}')">
                                ${statusLabelText(row.status)}
                            </button>
                        </div>
                        <div class="mt-1 small text-muted d-flex flex-wrap gap-2">
                            ${outingMetaHtml}
                        </div>
                    </div>
                `;
            }).join('');
        } catch (_e) {
            list.innerHTML = '<div class="text-danger small">상태 조회 실패</div>';
        }
    }

    async function handleWorkerStatusClickHome(userName, currentStatus) {
        const decodedName = decodeURIComponent(userName || '');
        const decodedStatus = decodeURIComponent(currentStatus || '사무실');
        const ok = await saveWorkerStatusPatch(decodedName, { status: nextStatus(decodedStatus) });
        if (!ok) return;
        await Promise.all([loadWorkerStatusHome(), loadOverview()]);
    }

    async function handleWorkerLocationClickHome(userName, currentLocation) {
        const decodedName = decodeURIComponent(userName || '');
        const decodedLocation = decodeURIComponent(currentLocation || '');
        const next = prompt('행선(목적지)을 입력하세요.', decodedLocation || '');
        if (next === null) return;
        const ok = await saveWorkerStatusPatch(decodedName, { location: next.trim() });
        if (!ok) return;
        await Promise.all([loadWorkerStatusHome(), loadOverview()]);
    }

    async function handleWorkerUntilClickHome(userName, currentUntil) {
        const decodedName = decodeURIComponent(userName || '');
        const decodedUntil = decodeURIComponent(currentUntil || '');
        const currentText = formatReturnTime(decodedUntil);
        workerReturnTimeTargetUser = decodedName;
        const sliderEl = document.getElementById('workerReturnTimeSlider');
        if (!sliderEl) return;
        sliderEl.value = String(timeTextToHalfHourIndex(currentText || ''));
        updateWorkerReturnTimePreviewHome();
        if (workerReturnTimeModal) workerReturnTimeModal.show();
    }

    function shiftWorkerReturnTimeHome(deltaMinutes) {
        const sliderEl = document.getElementById('workerReturnTimeSlider');
        if (!sliderEl) return;
        const step = deltaMinutes >= 0 ? 1 : -1;
        const current = Number(sliderEl.value) || 0;
        const next = ((current + step) % 48 + 48) % 48;
        sliderEl.value = String(next);
        updateWorkerReturnTimePreviewHome();
    }

    function updateWorkerReturnTimePreviewHome() {
        const sliderEl = document.getElementById('workerReturnTimeSlider');
        const previewEl = document.getElementById('workerReturnTimePreview');
        if (!sliderEl || !previewEl) return;
        previewEl.textContent = halfHourIndexToTimeText(sliderEl.value);
    }

    async function saveWorkerReturnTimeHome() {
        const target = workerReturnTimeTargetUser;
        if (!target) return;
        const sliderEl = document.getElementById('workerReturnTimeSlider');
        if (!sliderEl) return;
        const normalized = halfHourIndexToTimeText(sliderEl.value);
        const nextUntil = normalized ? `${formatLocalDateYYYYMMDD()}T${normalized}` : '';
        const ok = await saveWorkerStatusPatch(target, { until_time: nextUntil });
        if (!ok) return;
        if (workerReturnTimeModal) workerReturnTimeModal.hide();
        await Promise.all([loadWorkerStatusHome(), loadOverview()]);
    }

    async function clearWorkerReturnTimeHome() {
        const target = workerReturnTimeTargetUser;
        if (!target) return;
        const ok = await saveWorkerStatusPatch(target, { until_time: '' });
        if (!ok) return;
        if (workerReturnTimeModal) workerReturnTimeModal.hide();
        await Promise.all([loadWorkerStatusHome(), loadOverview()]);
    }

    async function loadFrequentSitesHome() {
        const box = document.getElementById('homeFrequentSiteList');
        try {
            const response = await fetch('/api/schedules/frequent-sites');
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                if (box) {
                    box.innerHTML = '<div class="text-danger small">바로가기 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</div>';
                }
                return;
            }
            const rows = Array.isArray(data.data) ? data.data : [];
            if (rows.length === 0) {
                renderShortcutGridHome([]);
                return;
            }
            const normalized = rows.slice(0, 8).map((row) => ({
                title: row.title || '이름 없는 사이트',
                url: row.url || '#',
                icon: '🔗',
            }));
            renderShortcutGridHome(normalized);
        } catch (_e) {
            if (box) {
                box.innerHTML = '<div class="text-danger small">바로가기 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</div>';
            }
        }
    }

    async function initializeHomePage() {
        window.dashboardLoginModal = new bootstrap.Modal(document.getElementById('dashboardLoginModal'));
        workerReturnTimeModal = new bootstrap.Modal(document.getElementById('workerReturnTimeModal'));
        const ok = await ensureSession();
        if (!ok) return;
        const returnTimeSliderEl = document.getElementById('workerReturnTimeSlider');
        if (returnTimeSliderEl) {
            returnTimeSliderEl.addEventListener('input', updateWorkerReturnTimePreviewHome);
            returnTimeSliderEl.addEventListener('change', updateWorkerReturnTimePreviewHome);
        }
        updateWorkerReturnTimePreviewHome();
        updateNowLabel();
        await fetchMeAndPaint();
        renderProjectProgressHome();
        renderSalesProfitChartHome();
        await Promise.all([loadOverview(), loadWorkerStatusHome(), loadFrequentSitesHome()]);
        setInterval(() => {
            updateNowLabel();
            loadOverview();
            loadWorkerStatusHome();
            loadFrequentSitesHome();
        }, 60000);
    }

    window.loadWorkerStatusHome = loadWorkerStatusHome;
    window.handleWorkerStatusClickHome = handleWorkerStatusClickHome;
    window.handleWorkerLocationClickHome = handleWorkerLocationClickHome;
    window.handleWorkerUntilClickHome = handleWorkerUntilClickHome;
    window.shiftWorkerReturnTimeHome = shiftWorkerReturnTimeHome;
    window.updateWorkerReturnTimePreviewHome = updateWorkerReturnTimePreviewHome;
    window.saveWorkerReturnTimeHome = saveWorkerReturnTimeHome;
    window.clearWorkerReturnTimeHome = clearWorkerReturnTimeHome;
    window.loadFrequentSitesHome = loadFrequentSitesHome;

    window.addEventListener('load', initializeHomePage);
})();
