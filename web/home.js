(function () {
    // ─── 임시 실제 데이터 (6월 기준) ─────────────────────────────────────────
    // API 연동 시 MONTHLY_PROGRESS_DATA 배열과 JUN_TOTAL_PROGRESS 상수만 삭제하면 됩니다.

    // 현장별 6월 공정률 — 계획 수립 기준 (실적 미집계)
    // planAmt / actualAmt 단위: 천원 / 계획 외 공사는 총 공정률에만 반영, 슬라이드 미표시
    const MONTHLY_PROGRESS_DATA = [
        // 김무선
        { no: 'TY25-003', name: '안양 샘모루초교 지중화공사',                                               manager: '김무선', percent: 0,     planAmt: 35000,  actualAmt: 0    },
        { no: 'TY25-004', name: '군포중 지중화공사',                                                         manager: '김무선', percent: 0,     planAmt: 30000,  actualAmt: 0    },
        { no: '',         name: '남양 뉴타운배전간선 설치공사',                                              manager: '김무선', percent: 0,     planAmt: 75000,  actualAmt: 0    },
        { no: 'TY25-006', name: '과천부림동 지중화공사',                                                     manager: '김무선', percent: 0,     planAmt: 8000,   actualAmt: 0    },
        // 김상훈
        { no: 'SY26-002', name: '부림SW53외 26년경과 노후변압기선로 교체공사',                              manager: '김상훈', percent: 0,     planAmt: 36994,  actualAmt: 0    },
        { no: 'SY25-011', name: '대농2 맨홀 내 저압접속 불량개소 보수공사',                                 manager: '김상훈', percent: 0,     planAmt: 1706,   actualAmt: 0    },
        { no: 'SY26-010', name: '경수SW48 불량 경과지 관로 계통 보강공사',                                  manager: '김상훈', percent: 0,     planAmt: 11238,  actualAmt: 0    },
        { no: 'SY25-020', name: '경수TR24외 26년경과 노후변압기선로 교체공사',                              manager: '김상훈', percent: 0,     planAmt: 30190,  actualAmt: 0    },
        { no: 'SY25-032', name: '안양동 682-3 현대건설 지중외상고장 복구공사(에스제이이)',                  manager: '김상훈', percent: 0,     planAmt: 5747,   actualAmt: 0    },
        { no: 'SY26-016', name: '부림SW5 외 수명만료 노후 지중케이블 교체공사',                             manager: '김상훈', percent: 0,     planAmt: 45588,  actualAmt: 0    },
        { no: 'SG26-005', name: '26년 특정제원 지상개폐기 교체공사',                                        manager: '김상훈', percent: 0,     planAmt: 14899,  actualAmt: 0    },
        { no: 'SG26-011', name: '특정제원(이엔테크제) 지상개폐기 교체공사(하안249, 하안138-2)',              manager: '김상훈', percent: 0,     planAmt: 2459,   actualAmt: 0    },
        { no: 'SG26-004', name: '하안259 지상개폐기 교체공사(PT불량)',                                      manager: '김상훈', percent: 0,     planAmt: 1131,   actualAmt: 0    },
        // 이재규
        { no: 'JY26-045', name: '학의동1181 리젠시빌주택 고압 200kw 신설_3206',                             manager: '이재규', percent: 150.1, planAmt: 1086,   actualAmt: 1630 },
        { no: 'JY25-256', name: '호계동553-1 평촌어반밸리 10,750kw 신설_3746',                              manager: '이재규', percent: 0,     planAmt: 2677,   actualAmt: 0    },
        { no: 'JY25-053', name: '안양동 97-3 안양1동진흥아파트주택재건축정비사업조합 주택용 3kw 신설',      manager: '이재규', percent: 0,     planAmt: 259,    actualAmt: 0    },
        { no: 'JY25-054', name: '안양동 165-1 안양1동진흥아파트주택재건축정비사업조합 가로등(갑) 1kw 신설', manager: '이재규', percent: 78.7,  planAmt: 259,    actualAmt: 204  },
        { no: 'JY26-057', name: '고천동 526-7 이인성 저압 35kw 신설',                                       manager: '이재규', percent: 100.1, planAmt: 925,    actualAmt: 925  },
        { no: 'JY26-051', name: '관양동 1385-3 ㈜한미건설 임시 20kw 신설',                                  manager: '이재규', percent: 0,     planAmt: 17,     actualAmt: 0    },
        { no: 'JY26-042', name: '박달동 15-17 조인준 일반용(갑)저압 10kw 신설',                             manager: '이재규', percent: 100.2, planAmt: 405,    actualAmt: 406  },
        { no: 'JY26-043', name: '고천나구역 초등학교부지 일반용(을)고압A 950kw 신설',                       manager: '이재규', percent: 0,     planAmt: 9903,   actualAmt: 0    },
        { no: 'JG26-028', name: '광명동 광명시장 일반용 850kw 신설_3167',                                   manager: '이재규', percent: 0,     planAmt: 1002,   actualAmt: 0    },
        { no: 'JY25-172', name: '내손라구역 GS건설 300kW 신설(상가용)',                                     manager: '이재규', percent: 0,     planAmt: 1137,   actualAmt: 0    },
        { no: 'JY25-165', name: '내손라구역 대우건설 160kW 신설공사 (상가용)',                              manager: '이재규', percent: 0,     planAmt: 395,    actualAmt: 0    },
        { no: 'JY25.260', name: '안양동 413-1 ㈜대영플러스 일반용(갑)저압 120kW 신설 외 1',                manager: '이재규', percent: 0,     planAmt: 7472,   actualAmt: 0    },
        { no: 'JY26-011', name: '관양동1020-1 현대드림모터스 89kw 증설_3040',                              manager: '이재규', percent: 0,     planAmt: 14296,  actualAmt: 0    },
        { no: 'JY26-022', name: '(지중)하안동 광명시청 일반용(갑)저압 300kw 신설(상용/임시)',              manager: '이재규', percent: 0,     planAmt: 15102,  actualAmt: 0    },
        // 김단후
        { no: 'MY25-001', name: '수암천 하천정비 및 주차장,공사 조성사업 전기공사',                        manager: '김단후', percent: 0,     planAmt: 76363,  actualAmt: 0    },
    ];

    // 6월 총 공정현황 (2026-06-04 기준)
    // 총 공정률 = (계획 실적 + 계획 외 실적) / 계획 목표금액
    const JUN_TOTAL_PROGRESS    = 2.5;
    const JUN_PLAN_ACTUAL_AMT   = 3165;   // 천원 — 계획 공사 실적
    const JUN_EXTRA_ACTUAL_AMT  = 7435;   // 천원 — 계획 외 공사 실적
    const JUN_TOTAL_ACTUAL_AMT  = 10599;  // 천원 — 합계
    const JUN_TOTAL_PLAN_AMT    = 429250; // 천원 — 계획 목표금액
    // ─────────────────────────────────────────────────────────────────────────

    const SALES_PROFIT_SAMPLE = {
        labels: ['1월', '2월', '3월', '4월', '5월', '6월', '7월', '8월', '9월', '10월', '11월', '12월'],
        profit:  [148077095, 273019042, 221839141, 173332713, 66160062,  -3759028, 0, 0, 0, 0, 0, 0],
        input:   [148259959, 330219307, 164792941, 149930938, 95582937,  14561960, 0, 0, 0, 0, 0, 0],
        outcome: [296337055, 603238349, 386632082, 323263651, 161742999, 10802931, 0, 0, 0, 0, 0, 0],
    };

    let salesProfitChart = null;
    let projectProgressCarousel = null;
    let workerReturnTimeModal = null;
    let workerReturnTimeTargetUser = '';

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

    function toMillionUnit(value) {
        return Math.round((Number(value) || 0) / 1000000);
    }

    function sumNumbers(values) {
        return (Array.isArray(values) ? values : []).reduce((acc, cur) => acc + (Number(cur) || 0), 0);
    }

    function formatMillionLabel(rawWon) {
        const million = toMillionUnit(rawWon);
        return `${million.toLocaleString('ko-KR')}백만원`;
    }

    function renderProjectProgressHome() {
        const inner = document.getElementById('projectProgressCarouselInner');
        const indicators = document.getElementById('projectProgressCarouselIndicators');
        if (!inner || !indicators) return;
        const carouselRoot = document.getElementById('projectProgressCarousel');
        if (!carouselRoot) return;

        const perSlide = 5;
        const pages = chunkArray(MONTHLY_PROGRESS_DATA, perSlide);

        inner.innerHTML = pages.map((group, pageIdx) => `
            <div class="carousel-item ${pageIdx === 0 ? 'active' : ''}">
                <div class="progress-slide-stack">
                    ${Array.from({ length: perSlide }).map((_, cardIdx) => {
                        const item = group[cardIdx] || null;
                        if (!item) {
                            return '<div class="progress-slide-card is-placeholder" aria-hidden="true"></div>';
                        }
                        const rawPercent = Number(item.percent) || 0;
                        const barPercent = Math.max(0, Math.min(100, rawPercent));
                        const amtLabel = item.planAmt != null
                            ? (item.planAmt === 0
                                ? `<span class="progress-meta-amt">${(item.actualAmt || 0).toLocaleString('ko-KR')}천원 (계획 외)</span>`
                                : `<span class="progress-meta-amt">${(item.actualAmt || 0).toLocaleString('ko-KR')} / ${item.planAmt.toLocaleString('ko-KR')}천원</span>`)
                            : '';
                        const metaText = `${escapeHtml(item.no)}${item.manager ? ' · ' + escapeHtml(item.manager) : ''}`;
                        return `
                        <div class="progress-slide-card">
                            <div class="d-flex justify-content-between align-items-center gap-2">
                                <div class="progress-project" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</div>
                                <div class="progress-percent">${rawPercent}%</div>
                            </div>
                            <div class="progress mt-2" role="progressbar" aria-label="공정률 ${rawPercent}%">
                                <div class="progress-bar bg-success" style="width:${barPercent}%"></div>
                            </div>
                            <div class="d-flex justify-content-between align-items-center mt-1 gap-2">
                                <div class="progress-meta text-truncate" title="${metaText}">${metaText}</div>
                                ${amtLabel}
                            </div>
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

        // 슬라이드 전환 시 레이아웃 높이 흔들림 방지: 첫 슬라이드(항상 만석)의 실제 높이로 inner를 고정
        requestAnimationFrame(() => {
            const activeItem = inner.querySelector('.carousel-item.active');
            if (activeItem) inner.style.minHeight = activeItem.offsetHeight + 'px';
        });

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
                        data: SALES_PROFIT_SAMPLE.profit.map(toMillionUnit),
                        backgroundColor: 'rgba(222, 102, 43, 0.85)',
                        borderColor: 'rgba(191, 78, 25, 1)',
                        borderWidth: 1,
                    },
                    {
                        label: '투입금액',
                        data: SALES_PROFIT_SAMPLE.input.map(toMillionUnit),
                        backgroundColor: 'rgba(119, 177, 67, 0.85)',
                        borderColor: 'rgba(95, 149, 48, 1)',
                        borderWidth: 1,
                    },
                    {
                        label: '성과금액',
                        data: SALES_PROFIT_SAMPLE.outcome.map(toMillionUnit),
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
                    tooltip: {
                        callbacks: {
                            label(context) {
                                const label = context.dataset.label || '';
                                const value = Number(context.parsed.y || 0).toLocaleString('ko-KR');
                                return `${label}: ${value}백만원`;
                            },
                        },
                    },
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: '백만원',
                        },
                        ticks: {
                            callback(value) {
                                return `${Number(value).toLocaleString('ko-KR')}M`;
                            },
                        },
                    },
                },
            },
        });

        const totalOutcomeEl = document.getElementById('totalOutcomeValue');
        const totalInputEl = document.getElementById('totalInputValue');
        const totalProfitEl = document.getElementById('totalProfitValue');
        if (totalOutcomeEl) totalOutcomeEl.textContent = formatMillionLabel(sumNumbers(SALES_PROFIT_SAMPLE.outcome));
        if (totalInputEl) totalInputEl.textContent = formatMillionLabel(sumNumbers(SALES_PROFIT_SAMPLE.input));
        if (totalProfitEl) totalProfitEl.textContent = formatMillionLabel(sumNumbers(SALES_PROFIT_SAMPLE.profit));
    }

    function renderTotalProgressChartHome() {
        // API 연동 시 아래 세 상수를 API 응답값으로 교체
        const progress = Math.max(0, Math.min(100, JUN_TOTAL_PROGRESS));
        const remain = Math.round((Math.max(0, 100 - progress)) * 10) / 10;
        const donutEl = document.getElementById('totalProgressDonut');
        const valueEl = document.getElementById('totalProgressValue');
        const doneEl = document.getElementById('totalProgressLegendDone');
        const remainEl = document.getElementById('totalProgressLegendRemain');
        const amtEl = document.getElementById('totalProgressAmount');
        if (!donutEl || !valueEl || !doneEl || !remainEl) return;
        donutEl.style.setProperty('--progress', String(progress));
        valueEl.textContent = `${progress}%`;
        doneEl.textContent = `진행 ${progress}%`;
        remainEl.textContent = `미달성 ${remain}%`;
        if (amtEl) {
            amtEl.innerHTML =
                `<span style="white-space:nowrap;">실적 <b>${JUN_TOTAL_ACTUAL_AMT.toLocaleString('ko-KR')}천원</b></span>` +
                `<br><span style="font-size:0.76rem;color:#7a8fa3;font-weight:500;white-space:nowrap;">(계획 ${JUN_PLAN_ACTUAL_AMT.toLocaleString('ko-KR')} + 계획외 ${JUN_EXTRA_ACTUAL_AMT.toLocaleString('ko-KR')}천원)</span>` +
                `<br><span style="white-space:nowrap;">목표 <b>${JUN_TOTAL_PLAN_AMT.toLocaleString('ko-KR')}천원</b></span>`;
        }
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
            showSaveToast(data.detail || '상태 저장 실패', 'error');
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
                            <span class="worker-outing-meta">
                                <button type="button" class="btn btn-link btn-sm p-0 text-decoration-none"
                                    onclick="handleWorkerLocationClickHome('${encodeURIComponent(row.user_name)}','${encodeURIComponent(row.location || '')}')">${locationLabel}</button>
                                <span>|</span>
                                <button type="button" class="btn btn-link btn-sm p-0 text-decoration-none"
                                    onclick="handleWorkerUntilClickHome('${encodeURIComponent(row.user_name)}','${encodeURIComponent(row.until_time || '')}')">${returnLabel}</button>
                            </span>
                    `
                    : '';
                return `
                    <div class="worker-row">
                        <div class="d-flex justify-content-between align-items-center gap-2">
                            <div class="worker-main-line">
                                <b class="worker-name">${escapeHtml(row.user_name)}</b>
                                ${outingMetaHtml}
                            </div>
                            <button type="button" class="btn btn-sm badge ${statusBadgeClass(row.status)}"
                                onclick="handleWorkerStatusClickHome('${encodeURIComponent(row.user_name)}','${encodeURIComponent(row.status || '사무실')}')">
                                ${statusLabelText(row.status)}
                            </button>
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
        renderTotalProgressChartHome();
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
