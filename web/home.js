(function () {
    // ═══════════════════════════════════════════════════════════════════════
    //  연동 주소
    // ───────────────────────────────────────────────────────────────────────
    //  WEATHER_API_BASE: 날씨는 CORS/키 보호를 위해 백엔드 프록시(`/api/weather/current`) 경유.
    //  자재 현황·진행중 공사 지도는 2026-11-12 홈에서 제거(연간 PR-3) — 연간 표 자리를 만들고,
    //  안 보이는 카드가 ERP 자재 API·카카오 지오코딩을 60초마다 계속 부르지 않게 로더째 뺐다.
    const WEATHER_API_BASE = '/api/weather/current';
    const ERP_MONTHLY_KPI_API = '/api/erp/monthly-kpi';
    const MONTHLY_PROGRESS_CONFIG_API = '/api/erp/monthly-progress-config';
    // 계획/실적 표 ‹ › 왼쪽 끝. ERP gongmu/_lib/주차.ts 의 최소월과 같은 값 — 바꾸면 ERP 도 같이(어긋나면 ERP 가 400 으로 알린다)
    const MIN_PLAN_MONTH = '2026-09';
    // 지난 달을 보다 이만큼 지나면 이번 달로 돌아온다 — 전자칠판에 지난 달이 하루 종일 떠 있지 않게
    const VIEW_RETURN_MS = 5 * 60 * 1000;
    const MONTH_RE = /^\d{4}-(0[1-9]|1[0-2])$/;
    // ═══════════════════════════════════════════════════════════════════════

    // 6월 총 공정현황 (2026-06-18 기준)
    const JUN_DATA_UPDATED      = '2026-06-18';
    const JUN_TOTAL_PROGRESS    = 34.8;
    const JUN_PLAN_ACTUAL_AMT   = 134362; // 천원 — 계획 공사 실적
    const JUN_EXTRA_ACTUAL_AMT  = 14958;  // 천원 — 계획 외 공사 실적
    const JUN_TOTAL_ACTUAL_AMT  = 149320; // 천원 — 합계
    const totalProgressState = {
        label: '6월',
        totalProgress: JUN_TOTAL_PROGRESS,
        actualAmountThousand: JUN_TOTAL_ACTUAL_AMT,
        actualFromErp: false,
        actualDetailText: `(계획 ${JUN_PLAN_ACTUAL_AMT.toLocaleString('ko-KR')} + 계획외 ${JUN_EXTRA_ACTUAL_AMT.toLocaleString('ko-KR')}천원)`,
        updatedAt: JUN_DATA_UPDATED,
        sourceLabel: '',
        // ERP가 내려준 공사별 실적 내역. null이면 상세를 보여줄 수 없다(구버전 ERP 또는 조회 실패).
        breakdown: null,
        // ERP split.settlement(그 달 끊은 계산서). null + settlementEnabled=true 면 "정산 불러오지 못함".
        settlement: null,
        // split.construction 을 받았을 때만 true — 대체값으로 그리는 중에는 정산 줄 자체를 안 그린다
        settlementEnabled: false,
        // ERP split 의 달('YYYY-MM')과 집계 기간 [from, to). 달력 월이 아니라 금요일 기준 주차의 달이다
        // (ERP 공무 화면·주간업무 보고서와 같은 규칙 — 9/28(월)부터 10월). 목표도 이 달로 불러온다.
        // '' 이면 옛 ERP·대체값 — 목표는 서버의 달력 월로 불러온다.
        erpMonth: '',
        periodFrom: '',
        periodTo: '',
        // 관리자 페이지에서 넣은 그 달 목표 행. { construction:{rows,totalThousand}, settlement:{...} }
        // null 은 '아직 못 받음'이고, 행이 0개인 것('목표 미등록')과는 다른 상황이다.
        // 목표 총액은 따로 저장하지 않는다 — 도넛 분모도 팝업 합계도 이 rows 의 합에서만 나온다.
        targets: null,
        // 담당자 선택지(서버 target_managers 표). 그래프는 이 순서로 그리고 '미지정'을 맨 끝에 붙인다.
        managers: [],
        // 계획외 공사의 담당 지정 { 지중No → 담당 }. 시공·정산 둘 다 이 담당의 실적에 합쳐진다(목표에는 안 들어감)
        unplannedOwner: new Map(),
    };
    // 목표 상세 팝업이 지금 보여주는 종류(시공/정산). 정렬 상태는 tableSortState 에 따로 둔다.
    // 표·도넛·담당자 그래프·팝업이 함께 보는 달.
    //   latestMonth : month 없는 응답의 split.month(금요일 기준 금주 달) = ‹ › 오른쪽 끝. '' = 아직 모름 → ‹ › 둘 다 막음
    //   viewMonth   : '' = 이번 달(latestMonth 를 따름), 'YYYY-MM' = 지난 달을 보는 중
    //   loading     : ‹ › 직후 응답 전 — 옛 달 숫자를 새 달 제목 아래 남겨 두지 않으려고 '…'로 비운다
    //   actualError : 지난 달 실적(month 경로)을 못 받음 — 0 이나 6월 대체값으로 채우지 않는다
    const monthNavState = { latestMonth: '', viewMonth: '', viewSince: 0, loading: false, actualError: false };
    // 로드 순번. 응답을 기다린 뒤 이 값이 바뀌어 있으면(그 사이 ‹ › 나 60초 갱신이 새로 시작됨) 아무것도 적용하지 않는다
    let totalProgressLoadSeq = 0;
    // 지금 targets 가 어느 달의 목표인지. 목표 조회가 실패했을 때 다른 달 목표를 남겨 두지 않으려고 기억한다
    let targetsMonth = '';
    const targetModalState = { kind: 'construction' };
    // 상세 팝업 셋이 지금 누구 몫을 보여주는지. type: 'all'(도넛 캡션) | 'manager'(담당자 줄, name) | 'unplanned'(계획외 실적 줄)
    const detailScopeState = { type: 'all', name: '' };
    // ─────────────────────────────────────────────────────────────────────────

    // 담당자별 색상/약칭 (담당자별 진척 그래프)
    const MANAGER_STYLE = {
        '김무선': { color: '#2f6fed', short: '무선' },
        '김상훈': { color: '#e8590c', short: '상훈' },
        '이재규': { color: '#2f9e44', short: '이재' },
        '김단후': { color: '#ae3ec9', short: '단후' },
    };
    const DEFAULT_MANAGER_STYLE = { color: '#64748b', short: '담당' };
    // 담당자별 진척 그래프에서 MANAGER_STYLE 에 없는 담당자에게 주는 예비 색
    const EXTRA_MANAGER_COLORS = ['#0ca678', '#f08c00', '#1098ad', '#d6336c', '#5c7cfa', '#868e96'];

    function managerStyle(name) {
        return MANAGER_STYLE[String(name || '').trim()] || DEFAULT_MANAGER_STYLE;
    }

    function updateNowLabel() {
        const days = ['일', '월', '화', '수', '목', '금', '토'];
        const now = new Date();
        const text = `${now.getFullYear()}.${String(now.getMonth() + 1).padStart(2, '0')}.${String(now.getDate()).padStart(2, '0')} (${days[now.getDay()]})`;
        const el = document.getElementById('homeNowLabel');
        if (el) el.textContent = text;
        const badge = document.getElementById('weatherDateBadge');
        if (badge) badge.textContent = `오늘 ${String(now.getMonth() + 1).padStart(2, '0')}.${String(now.getDate()).padStart(2, '0')}`;
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

    function renderTotalProgressChartHome() {
        const percent = getTotalProgressPercent();
        const settle = getSettlementPercent();
        const donutEl = document.getElementById('totalProgressDonut');
        const valueEl = document.getElementById('totalProgressValue');
        const settleEl = document.getElementById('totalProgressSettleValue');
        const settleRowEl = document.getElementById('totalProgressSettleRow');
        const settleLegendEl = document.getElementById('totalProgressLegendSettle');
        const amtEl = document.getElementById('totalProgressAmount');
        const titleEl = document.getElementById('totalProgressTitle');
        if (!donutEl || !valueEl) return;
        const label = totalProgressState.label || '6월';
        if (titleEl) titleEl.textContent = `${label} 총 공정률`;
        // 못 받음(targets=null)과 목표 미등록(행 0개)은 캡션과 같은 말로 구분한다 — 고칠 곳이 다르다.
        // 도넛 가운데는 좁아서 '목표 미등록' 대신 '미등록'으로 줄인다(캡션에 전체 문구가 있다).
        // 실적을 못 받았는데 목표가 있으면 '미등록'이 찍힌다 — 고칠 곳(관리자 입력)을 잘못 가리키므로 실적 쪽 사정이 먼저다
        const noTargetText = (monthNavState.loading || monthNavState.actualError || !totalProgressState.targets) ? '-' : '미등록';
        donutEl.style.setProperty('--progress', String(percent === null ? 0 : Math.min(100, percent)));
        valueEl.textContent = percent === null ? noTargetText : `${percent}%`;

        // 안쪽 링(정산). 대체값 화면에선 정산을 아예 안 받았으므로 링·가운데 줄·범례를 모두 감춘다.
        const showSettle = settle.state !== 'hidden';
        donutEl.classList.toggle('no-settle', !showSettle);
        if (settleRowEl) settleRowEl.style.display = showSettle ? '' : 'none';
        if (settleLegendEl) settleLegendEl.style.display = showSettle ? '' : 'none';
        donutEl.style.setProperty('--settle', String(settle.state === 'ok' ? Math.min(100, settle.value) : 0));
        if (settleEl) {
            settleEl.textContent = settle.state === 'ok' ? `${settle.value}%`
                : settle.state === 'notarget' ? '미등록' : '-';
        }
        if (amtEl) {
            // 지난 달 로딩·실패 — 0 을 찍지 않는다(진짜 0 과 구분되게). 목표 조각은 그대로 붙여 목표는 보이게 한다
            if (monthNavState.loading || monthNavState.actualError) {
                const msg = monthNavState.loading ? '불러오는 중…' : '실적 불러오지 못함';
                amtEl.innerHTML =
                    `<span style="color:${monthNavState.loading ? '#8a99ab' : '#b42318'};">${msg}</span>` +
                    buildTargetFractionHtml('construction');
                renderManagerProgressHome();
                renderPlanActualTableHome();
                return;
            }
            const detailHtml = totalProgressState.actualDetailText
                ? `<br><span style="font-size:0.74rem;color:#7a8fa3;font-weight:500;white-space:nowrap;">${escapeHtml(totalProgressState.actualDetailText)}</span>`
                : '';
            const sourceText = totalProgressState.sourceLabel ? ` ${totalProgressState.sourceLabel}` : '';
            // ERP에서 시공 실적을 받았을 때만 '시공 실적'이라 부른다 — 대체값은 무엇의 합인지 보장할 수 없다
            const actualLabel = totalProgressState.actualFromErp ? '시공' : '실적';
            // 정산은 시공과 더하는 숫자가 아니다(대부분 이미 시공으로 잡힌 일의 청구) — 별도 줄로만 보여준다
            let settlementHtml = '';
            if (totalProgressState.settlementEnabled) {
                const s = totalProgressState.settlement;
                settlementHtml = s
                    ? `<br><span class="tp-clickable" role="button" tabindex="0" data-tp-open="settlement">` +
                          `정산 <b>${Number(s.totalThousand).toLocaleString('ko-KR')}</b></span>` +
                      buildTargetFractionHtml('settlement')
                    : `<br><span style="font-size:0.74rem;color:#aab8c6;white-space:nowrap;">정산 불러오지 못함</span>`;
            }
            // 목표는 자기 실적 바로 뒤에 '/ 목표'로 붙인다 — 목표를 별도 줄로 두면 바로 위 줄의 목표처럼 읽힌다
            amtEl.innerHTML =
                `<span class="tp-clickable" role="button" tabindex="0" data-tp-open="actual">` +
                    `${actualLabel} <b>${Number(totalProgressState.actualAmountThousand || 0).toLocaleString('ko-KR')}</b></span>` +
                buildTargetFractionHtml('construction') +
                detailHtml +
                settlementHtml +
                `<br><span style="font-size:0.71rem;color:#aab8c6;white-space:nowrap;">최신화${sourceText} ${escapeHtml(totalProgressState.updatedAt)}</span>`;
        }
        // 담당자 그래프는 도넛과 같은 상태(targets·breakdown·settlement)에서 그린다 — 도넛이 다시 그려질 때 항상 같이
        renderManagerProgressHome();
        renderPlanActualTableHome();
    }

    // 담당자 한 줄(시공 또는 정산). 100%에서 자르지 않는다 — 계획보다 얼마나 부족/초과했는지가 다음 달 계획을 고치는 근거다.
    // (부족/초과 금액 글씨는 사장님 요청으로 뺐다 — %와 '실적 / 목표'로 읽는다)
    // 넘치면 막대 전체를 실적 기준으로 줄이고, 목표 지점에 세로 눈금을 세운다(눈금 오른쪽이 초과분).
    // 실적·목표 숫자는 누르면 그 담당자 몫의 상세가 뜬다(도넛 캡션과 같은 자리 규칙). 보여줄 행이 없는 숫자('-'·'목표 없음')는 누르지 않게 둔다.
    function buildManagerLineHtml(kindClass, label, cell, name) {
        const fmt = (n) => Number(n).toLocaleString('ko-KR');
        const hasActual = cell.actualThousand !== null;
        const scopeAttr = `data-tp-scope="manager" data-tp-mgr="${escapeHtml(name)}"`;
        const clickable = (open, text) =>
            `<span class="tp-clickable" role="button" tabindex="0" data-tp-open="${open}" ${scopeAttr}>${text}</span>`;
        const actualText = hasActual
            ? clickable(kindClass === 'construction' ? 'actual' : 'settlement', fmt(cell.actualThousand))
            : '-';
        const targetText = cell.targetThousand ? clickable(`target-${kindClass}`, fmt(cell.targetThousand)) : '목표 없음';
        const pct = hasActual && cell.targetThousand > 0
            ? Math.round((cell.actualThousand / cell.targetThousand) * 1000) / 10
            : null;
        const scale = pct === null ? 100 : Math.max(100, pct);
        const width = pct === null ? 0 : (pct / scale) * 100;
        const marker = pct !== null && pct > 100
            ? `<i class="mgr-goal" style="left:${(100 / scale) * 100}%"></i>` : '';
        return `<div class="mgr-line ${kindClass}"><span>${label}</span>` +
            `<div class="mgr-bar"><span style="width:${width}%"></span>${marker}</div>` +
            `<span class="mgr-val"><b>${pct === null ? '-' : `${pct}%`}</b>${actualText} / ${targetText}</span></div>`;
    }

    function renderManagerProgressHome() {
        const listEl = document.getElementById('managerProgressList');
        if (!listEl) return;
        const t = totalProgressState.targets;
        if (!t) {
            // 달을 옮기는 중엔 목표를 비워 둔 것이지 실패가 아니다 — 같은 모양으로 '불러오는 중'을 보인다
            const msg = monthNavState.loading ? '불러오는 중…' : '목표를 불러오지 못했습니다.';
            listEl.innerHTML = `<div class="text-muted small">${msg}</div>`;
            return;
        }
        if (!t.construction.rows.length && !t.settlement.rows.length) {
            listEl.innerHTML = '<div class="text-muted small">이번 달 목표 행이 없습니다(관리자 페이지에서 등록).</div>';
            return;
        }
        // 대체값 화면(ERP 시공 실적 없음)에선 breakdown 이 null — 실적 '-'로 목표만 보여준다
        const construction = getManagerProgress('construction');
        const showSettle = totalProgressState.settlementEnabled;
        const settlement = getManagerProgress('settlement');
        const empty = (actual) => ({ targetThousand: 0, actualThousand: actual ? 0 : null });
        const cell = (map, name, actual) => map.get(name) || empty(actual);
        const fmt = (n) => Number(n).toLocaleString('ko-KR');

        // 목록에 없는 이름(목록에서 빠진 옛 담당자)이 행에 남아 있으면 그 칸도 그린다 — 안 그리면 그 금액이 그래프에서 사라진다
        const names = [...totalProgressState.managers];
        [...construction.buckets.keys(), ...settlement.buckets.keys()].forEach((n) => { if (n && !names.includes(n)) names.push(n); });
        // 옛 미지정 행이 남아 있을 때만 그 칸을 그린다(관리자 화면에서 지정하면 사라진다) — 안 그리면 그 금액이 합계에서 빠진다
        if (construction.buckets.has('') || settlement.buckets.has('')) names.push('');

        const rowsHtml = names.map((name, idx) => {
            // MANAGER_STYLE 에 없는 새 담당자(관리자 화면에서 추가)는 회색이면 구분이 안 되므로 예비 색을 순서대로 준다
            const color = !name ? '#aab8c6' : (MANAGER_STYLE[name] ? MANAGER_STYLE[name].color : EXTRA_MANAGER_COLORS[idx % EXTRA_MANAGER_COLORS.length]);
            return `<div class="mgr-row${name ? '' : ' unassigned'}">` +
                `<div class="mgr-name"><i style="background:${color}"></i>${escapeHtml(name || '담당 미지정')}</div>` +
                buildManagerLineHtml('construction', '시공', cell(construction.buckets, name, totalProgressState.breakdown), name) +
                (showSettle ? buildManagerLineHtml('settlement', '정산', cell(settlement.buckets, name, totalProgressState.settlement), name) : '') +
                `</div>`;
        }).join('');

        // 계획외: 목표 행이 없는 공사의 실적. %는 없고 금액만 — 이 줄이 있어야 담당자 칸들의 합이 도넛 숫자와 같아진다
        // 누르면 담당도 목표도 없는 공사만 모은 상세가 뜬다 — 관리자 화면에서 누구에게 지정할지 고를 때 보는 목록
        const unplanned = (open, label, v) => (v === null
            ? `<span>${label} <b>-</b></span>`
            : `<span class="tp-clickable" role="button" tabindex="0" data-tp-open="${open}" data-tp-scope="unplanned">${label} <b>${fmt(v)}</b></span>`);
        // 행이 전부 ERP 담당을 달고 오면 그 종류의 계획외는 구조상 늘 0이다 — '0'을 그리면 "목표에 없는 공사가 없다"로 읽히니 칸째 뺀다.
        // (옛 ERP 이거나 담당을 버린 행이 하나라도 있으면 옛 규칙이 살아 있으므로 그린다)
        const breakdownRows = totalProgressState.breakdown ? totalProgressState.breakdown.rows : [];
        const constructionByErp = breakdownRows.length > 0 && breakdownRows.every((r) => Array.isArray(r.managers));
        const settlementRows = totalProgressState.settlement ? totalProgressState.settlement.rows : [];
        const settlementByErp = settlementRows.length > 0 && settlementRows.every((r) => typeof r.manager === 'string');
        const unplannedParts = (constructionByErp ? '' : unplanned('actual', '시공', construction.unplannedThousand)) +
            (showSettle && !settlementByErp ? unplanned('settlement', '정산', settlement.unplannedThousand) : '');
        const unplannedHtml = unplannedParts
            ? `<div class="mgr-unplanned"><span class="mgr-name-sm">계획외 실적</span>` + unplannedParts +
                `<span class="text-muted">목표에 없는 공사</span></div>`
            : '';
        listEl.innerHTML = rowsHtml + unplannedHtml;
    }

    // ══════════ 계획/실적 표 (PR-3) ══════════
    // 도넛·담당자 그래프와 같은 상태에서 그린다. 실행률은 도넛과 같은 함수(getTotalProgressPercent·getSettlementPercent)로 —
    // 표의 % 와 도넛의 % 가 같은 계산에서 나와 갈라질 자리가 없다. 100% 에서 자르지 않는다(설계 §7-3), 계획 0 이면 '—'(§7-5).
    function renderPlanActualTableHome() {
        const bodyEl = document.getElementById('planActualBody');
        if (!bodyEl) return;
        const fmt = (n) => Number(n).toLocaleString('ko-KR');
        const open = (which, text) => `<span class="tp-clickable" role="button" tabindex="0" data-tp-open="${which}">${text}</span>`;
        const nav = monthNavState;
        const shown = shownMonth();

        const monthEl = document.getElementById('planActualMonth');
        if (monthEl) monthEl.textContent = shown ? monthLabel(shown) : totalProgressState.label;
        const prevEl = document.getElementById('planActualPrev');
        const nextEl = document.getElementById('planActualNext');
        if (prevEl) prevEl.disabled = !shown || !nav.latestMonth || shiftMonth(shown, -1) < MIN_PLAN_MONTH;
        if (nextEl) nextEl.disabled = !shown || !nav.latestMonth || shown >= nav.latestMonth;
        const periodEl = document.getElementById('planActualPeriod');
        if (periodEl) periodEl.textContent = `단위 천원${periodSubText()}`;
        const noticeEl = document.getElementById('planActualNotice');
        if (noticeEl) {
            noticeEl.style.display = nav.actualError ? '' : 'none';
            noticeEl.textContent = nav.actualError ? 'ERP 실적을 불러오지 못했습니다 · 1분 뒤 다시 시도합니다' : '';
        }

        const t = totalProgressState.targets;
        const planCell = (kind) => {
            if (!t) return '<span class="pa-dim">-</span>';
            if (!t[kind].rows.length) return '<span class="pa-dim">미등록</span>';
            return open(`target-${kind}`, fmt(t[kind].totalThousand));
        };
        const actualCell = (kind) => {
            if (nav.loading) return '<span class="pa-dim">…</span>';
            if (nav.actualError) return '<span class="pa-fail">못 불러옴</span>';
            if (kind === 'construction') {
                // 대체값 화면(ERP 시공 실적 없음)에선 6월 숫자를 표로 옮기지 않는다
                const b = totalProgressState.actualFromErp ? totalProgressState.breakdown : null;
                return b ? open('actual', fmt(b.totalThousand)) : '<span class="pa-dim">-</span>';
            }
            if (!totalProgressState.settlementEnabled) return '<span class="pa-dim">-</span>';
            const s = totalProgressState.settlement;
            return s ? open('settlement', fmt(s.totalThousand)) : '<span class="pa-fail">못 불러옴</span>';
        };
        const rateCell = (kind) => {
            if (nav.loading) return '<span class="pa-dim">…</span>';
            if (kind === 'construction') {
                const pct = totalProgressState.actualFromErp ? getTotalProgressPercent() : null;
                return pct === null ? '<span class="pa-dim">—</span>' : `${pct}%`;
            }
            const s = getSettlementPercent();
            return s.state === 'ok' ? `${s.value}%` : '<span class="pa-dim">—</span>';
        };

        const row = (kind, label) =>
            `<div class="pa-k ${kind}">${label}</div><div>${planCell(kind)}</div><div>${actualCell(kind)}</div><div class="pa-rate">${rateCell(kind)}</div>`;
        bodyEl.innerHTML =
            '<div class="pa-h"></div><div class="pa-h">계획</div><div class="pa-h">실적</div><div class="pa-h">실행률</div>' +
            row('construction', '시공') + row('settlement', '정산');
    }

    // 캡션의 ' / 목표천원' 조각. 누르면 그 종류의 목표 상세가 열린다.
    // 아직 못 받았으면 '-', 받았는데 행이 없으면 '목표 미등록' — 둘은 고칠 곳이 다르다(네트워크 vs 관리자 입력).
    function buildTargetFractionHtml(kind) {
        const t = totalProgressState.targets;
        let text;
        if (!t) text = '-';
        else if (!t[kind].rows.length) text = '목표 미등록';
        else text = `<b>${t[kind].totalThousand.toLocaleString('ko-KR')}</b>천원`;
        return ` / <span class="tp-clickable" role="button" tabindex="0" data-tp-open="target-${kind}">${text}</span>`;
    }

    // ══════════ 총 공정률 실적 상세 팝업 ══════════

    // 날짜 한 칸의 표기. 기간이 금요일 기준 주차라 달을 넘나든다(9월 표에 8/31) —
    // 카드 제목의 달과 같은 날짜는 '일'만, 다른 달 날짜는 '월/일'로 적어 31일이 어느 달인지 헷갈리지 않게 한다.
    function formatPeriodDay(ymd) {
        const m = Number(ymd.slice(5, 7));
        const d = Number(ymd.slice(8, 10));
        const month = totalProgressState.erpMonth;
        return month && ymd.slice(0, 7) !== month ? `${m}/${d}` : String(d);
    }

    // 정산 표의 '일' 칸. 같은 달이면 '23일', 다른 달 계산서(주차 기간이 달을 넘음)면 '8/31'. 옛 ERP 응답이면 day 로.
    function formatSettlementDay(r) {
        if (r.date) {
            const text = formatPeriodDay(r.date);
            return text.includes('/') ? text : `${text}일`;
        }
        return r.day === null ? '' : `${r.day}일`;
    }

    // 공사명 아래 진행 날짜 한 줄.
    // 날짜가 없으면(그 달 작업 없이 준공만 반영된 공사) 줄 자체를 안 그린다 — 빈 줄도 시선을 뺏는다.
    function buildProgressDaysHtml(row) {
        // 전체 날짜(dates)가 있으면 그것으로, 옛 ERP 응답이면 '일'(days)로 그린다
        const items = (row.dates && row.dates.length)
            ? row.dates.map((ymd) => ({ text: formatPeriodDay(ymd), night: row.nightDates.includes(ymd) }))
            : (row.days || []).map((d) => ({ text: String(d), night: (row.nightDays || []).includes(d) }));
        if (!items.length) return '';
        const text = items
            .map((it) => (it.night
                ? `<span class="night">${it.text}(야간)</span>`
                : `<span class="n">${it.text}</span>`))
            .join('<span class="n">, </span>');
        return `<span class="tp-days">${text}</span>`;
    }

    // 팝업 부제에 붙일 집계 기간. 달력 월과 다르다는 걸 그 자리에서 말한다 — 안 그러면 ERP 홈 KPI(달력 월)와 숫자가 달라 보일 때 이유를 알 길이 없다.
    function periodSubText() {
        const { periodFrom: from, periodTo: to } = totalProgressState;
        if (!from || !to) return '';
        // to 는 미포함 — 마지막 날은 그 전날(일요일)이다. 날짜 산술은 UTC 자정에서만 해 기기 시간대에 흔들리지 않게 한다
        const last = new Date(`${to}T00:00:00Z`);
        last.setUTCDate(last.getUTCDate() - 1);
        const md = (ymd) => `${Number(ymd.slice(5, 7))}/${Number(ymd.slice(8, 10))}`;
        return ` · 기간 ${md(from)}~${md(last.toISOString().slice(0, 10))} (금요일 기준 주차)`;
    }

    // 팝업 제목에 끼울 '누구 몫' 글자. 전체면 빈 문자열.
    function detailScopeText() {
        if (detailScopeState.type === 'manager') return `${detailScopeState.name || '담당 미지정'} `;
        if (detailScopeState.type === 'unplanned') return '계획외 ';
        return '';
    }

    // 지금 범위에 해당하는 행. 담당자·계획외는 그래프가 쓰는 getManagerProgress 의 목록을 그대로 꺼낸다 — 거르는 규칙을 여기서 다시 쓰지 않는다.
    //   kind:  'construction' | 'settlement'
    //   which: 'actual'(실적 행) | 'target'(목표 행)
    //   allRows: 전체 범위일 때 쓸 원본 행
    function scopedDetailRows(kind, which, allRows) {
        if (detailScopeState.type === 'all') return allRows;
        const progress = getManagerProgress(kind);
        if (!progress) return [];
        if (detailScopeState.type === 'unplanned') return which === 'actual' ? progress.unplannedRows : [];
        const b = progress.buckets.get(detailScopeState.name);
        if (!b) return [];
        return which === 'actual' ? b.actualRows : b.targetRows;
    }

    function renderProgressActualModal() {
        const label = totalProgressState.label || '';
        const titleEl = document.getElementById('progressActualTitle');
        const subEl = document.getElementById('progressActualSub');
        const bodyEl = document.getElementById('progressActualBody');
        if (!bodyEl) return;
        const who = detailScopeText();
        if (titleEl) titleEl.textContent = totalProgressState.actualFromErp ? `${label} ${who}시공 상세` : `${label} ${who}실적 상세`;
        if (subEl) subEl.textContent = `ERP 최신화 ${totalProgressState.updatedAt || '-'}${periodSubText()}`;

        const breakdown = totalProgressState.breakdown;
        // 못 불러온 경우 빈 표를 띄우지 않는다 — 빈 표는 "실적이 0건"과 화면상 구분이 안 된다.
        if (!breakdown) {
            bodyEl.innerHTML = '<div class="tp-error">ERP에서 실적 상세를 불러오지 못했습니다.<br>' +
                '도넛에 보이는 숫자는 <b>최근 저장된 대체값</b>이라 상세와 맞지 않을 수 있습니다.</div>';
            return;
        }
        // 반대로 진짜로 0건인 달은 그렇게 말한다. 위 에러 문구를 재활용하면 없는 고장을 있다고 하는 것.
        // 합계는 보여주는 행의 합으로 다시 만든다 — 전체면 도넛 캡션 숫자, 담당자면 그 막대의 실적 숫자와 같은 배열에서 나온다
        const rows = scopedDetailRows('construction', 'actual', breakdown.rows);
        if (rows.length === 0) {
            bodyEl.innerHTML = `<div class="tp-empty">${escapeHtml(label)} ${escapeHtml(who)}실적이 아직 없습니다.</div>`;
            return;
        }

        const rowsHtml = sortDetailRows(rows, 'actual').map((r) => `<tr>` +
            `<td class="tp-no">${escapeHtml(r.jijungNo)}</td>` +
            `<td class="tp-name">${escapeHtml(r.name)}${buildProgressDaysHtml(r)}</td>` +
            `<td class="tp-amt ${r.amountThousand < 0 ? 'minus' : ''}">` +
                `${r.amountThousand.toLocaleString('ko-KR')}</td>` +
            `</tr>`).join('');

        bodyEl.innerHTML =
            `<div class="tp-table-wrap"><table class="tp-table">` +
                `<thead><tr>` +
                    sortableTh('actual', 'jijungNo', '지중No', 'width:110px;') +
                    `<th>공사명</th>` +
                    sortableTh('actual', 'amount', '실적 (천원)', 'width:130px;text-align:right;') +
                `</tr></thead>` +
                `<tbody>${rowsHtml}</tbody>` +
            `</table></div>` +
            `<div class="tp-foot">` +
                `<span class="lb">합계 <span style="font-weight:500;color:#4a7ab5;">(${rows.length}건)</span>` +
                    `<span class="match">       </span></span>` +
                `<span class="v">${sumThousand(rows).toLocaleString('ko-KR')} 천원</span>` +
            `</div>`;
    }

    function renderProgressSettlementModal() {
        const label = totalProgressState.label || '';
        const titleEl = document.getElementById('progressSettlementTitle');
        const subEl = document.getElementById('progressSettlementSub');
        const bodyEl = document.getElementById('progressSettlementBody');
        if (!bodyEl) return;
        const who = detailScopeText();
        if (titleEl) titleEl.textContent = `${label} ${who}정산 상세`;
        if (subEl) subEl.textContent = `기성·준공 계산서 · ERP 최신화 ${totalProgressState.updatedAt || '-'}${periodSubText()}`;

        const s = totalProgressState.settlement;
        if (!s) {
            bodyEl.innerHTML = '<div class="tp-error">ERP에서 정산 상세를 불러오지 못했습니다.</div>';
            return;
        }
        // 진짜로 0건인 달은 그렇게 말한다 — 위 에러 문구를 재활용하면 없는 고장을 있다고 하는 것
        // 합계는 보여주는 행의 합 — 담당자 범위면 그 담당자 정산 막대의 실적 숫자와 같은 배열이다
        const rows = scopedDetailRows('settlement', 'actual', s.rows);
        if (rows.length === 0) {
            bodyEl.innerHTML = `<div class="tp-empty">${escapeHtml(label)} ${escapeHtml(who)}끊은 계산서가 아직 없습니다.</div>`;
            return;
        }

        const rowsHtml = sortDetailRows(rows, 'settlement').map((r) => `<tr>` +
            `<td class="tp-no">${escapeHtml(r.jijungNo)}</td>` +
            `<td class="tp-name">${escapeHtml(r.name)}</td>` +
            `<td class="tp-kind">${escapeHtml(r.kind)}</td>` +
            `<td class="tp-kind" style="text-align:right;">${formatSettlementDay(r)}</td>` +
            `<td class="tp-amt ${r.amountThousand < 0 ? 'minus' : ''}">` +
                `${r.amountThousand.toLocaleString('ko-KR')}</td>` +
            `</tr>`).join('');

        bodyEl.innerHTML =
            `<div class="tp-table-wrap"><table class="tp-table">` +
                `<thead><tr>` +
                    sortableTh('settlement', 'jijungNo', '지중No', 'width:110px;') +
                    `<th>공사명</th>` +
                    `<th style="width:80px;">구분</th>` +
                    `<th style="width:50px;text-align:right;">일</th>` +
                    sortableTh('settlement', 'amount', '금액 (천원)', 'width:120px;text-align:right;') +
                `</tr></thead>` +
                `<tbody>${rowsHtml}</tbody>` +
            `</table></div>` +
            `<div class="tp-foot">` +
                `<span class="lb">합계 <span style="font-weight:500;color:#4a7ab5;">(${rows.length}건)</span>` +
                    `<span class="match">       </span></span>` +
                `<span class="v">${sumThousand(rows).toLocaleString('ko-KR')} 천원</span>` +
            `</div>`;
    }

    const TARGET_KIND_TEXT = { construction: '시공', settlement: '정산' };

    // 상세 팝업 셋(실적·정산·목표)의 정렬 상태. key 가 null 이면 서버가 보낸 순서 그대로 둔다.
    // 팝업을 닫았다 다시 열어도 유지한다 — 60초마다 ERP 값이 새로 와도 사용자가 고른 순서가 풀리지 않게.
    const tableSortState = {
        actual: { key: null, dir: 'asc' },
        settlement: { key: null, dir: 'asc' },
        target: { key: 'jijungNo', dir: 'asc' },
    };

    // 지중No는 문자열이라 그냥 비교하면 '99'가 '101'보다 뒤로 간다 — numeric 옵션으로 숫자 덩어리는 숫자로 비교한다
    function compareJijungNo(a, b) {
        return a.jijungNo.localeCompare(b.jijungNo, 'ko', { numeric: true });
    }

    // 원본 배열은 건드리지 않는다(slice) — 합계는 여전히 원본 rows 에서 나오고, 정렬은 보여주는 순서만 바꾼다
    function sortDetailRows(rows, table) {
        const { key, dir } = tableSortState[table];
        if (!key) return rows;
        const sign = dir === 'asc' ? 1 : -1;
        return rows.slice().sort((a, b) => {
            const diff = key === 'amount' ? a.amountThousand - b.amountThousand : compareJijungNo(a, b);
            // 금액이 같은 행끼리는 지중No 순으로 — 다시 그릴 때마다 순서가 흔들리지 않게
            return diff !== 0 ? diff * sign : compareJijungNo(a, b);
        });
    }

    function sortableTh(table, key, label, style) {
        const st = tableSortState[table];
        const arrow = st.key !== key ? '' : (st.dir === 'asc' ? ' ▲' : ' ▼');
        return `<th class="tp-sort" style="${style}" role="button" tabindex="0" data-tp-sort="${key}">${label}${arrow}</th>`;
    }

    // 같은 열을 다시 누르면 방향만 뒤집는다. 금액은 처음 누를 때 큰 것부터 — 보통 큰 공사부터 본다.
    function toggleDetailSort(table, key) {
        const st = tableSortState[table];
        if (st.key === key) {
            st.dir = st.dir === 'asc' ? 'desc' : 'asc';
        } else {
            st.key = key;
            st.dir = key === 'amount' ? 'desc' : 'asc';
        }
        if (table === 'actual') renderProgressActualModal();
        else if (table === 'settlement') renderProgressSettlementModal();
        else renderProgressTargetModal();
    }

    function renderProgressTargetModal() {
        const label = totalProgressState.label || '';
        const kind = targetModalState.kind;
        const kindText = TARGET_KIND_TEXT[kind];
        const titleEl = document.getElementById('progressTargetTitle');
        const bodyEl = document.getElementById('progressTargetBody');
        if (!bodyEl) return;
        const who = detailScopeText();
        if (titleEl) titleEl.textContent = `${label} ${who}${kindText} 목표 상세`;

        const t = totalProgressState.targets;
        if (!t) {
            bodyEl.innerHTML = '<div class="tp-error">목표를 불러오지 못했습니다.</div>';
            return;
        }
        const target = t[kind];
        if (!target.rows.length) {
            bodyEl.innerHTML = `<div class="tp-empty">${escapeHtml(label)} ${kindText} 목표가 아직 등록되지 않았습니다.<br>` +
                `<span style="font-size:0.79rem;">관리자 페이지 → 월별 총 공정률 목표 관리에서 추가할 수 있습니다.</span></div>`;
            return;
        }

        // 담당자 범위면 그 담당자 목표 행만 — 합계가 막대의 목표 숫자와 같은 배열에서 나온다
        const rows = scopedDetailRows(kind, 'target', target.rows);
        if (rows.length === 0) {
            bodyEl.innerHTML = `<div class="tp-empty">${escapeHtml(label)} ${escapeHtml(who)}${kindText} 목표 행이 없습니다.</div>`;
            return;
        }

        const rowsHtml = sortDetailRows(rows, 'target').map((r) => `<tr>` +
            `<td class="tp-no">${escapeHtml(r.jijungNo)}</td>` +
            `<td class="tp-name">${escapeHtml(r.name)}</td>` +
            `<td class="tp-amt">${r.amountThousand.toLocaleString('ko-KR')}</td>` +
            `</tr>`).join('');

        bodyEl.innerHTML =
            `<div class="tp-table-wrap"><table class="tp-table">` +
                `<thead><tr>` +
                    sortableTh('target', 'jijungNo', '지중No', 'width:110px;') +
                    `<th>공사명</th>` +
                    sortableTh('target', 'amount', '목표 (천원)', 'width:140px;text-align:right;') +
                `</tr></thead>` +
                `<tbody>${rowsHtml}</tbody>` +
            `</table></div>` +
            `<div class="tp-foot">` +
                `<span class="lb">합계 <span style="font-weight:500;color:#4a7ab5;">(${rows.length}건)</span></span>` +
                `<span class="v">${sumThousand(rows).toLocaleString('ko-KR')} 천원</span>` +
            `</div>`;
    }

    // scopeEl: 누른 글자. data-tp-scope 가 없으면(도넛 캡션) 전체 범위로 연다 — 직전에 담당자 팝업을 열었어도 범위가 남지 않게.
    function openProgressDetail(which, scopeEl) {
        const scope = scopeEl && scopeEl.dataset.tpScope;
        detailScopeState.type = scope === 'manager' || scope === 'unplanned' ? scope : 'all';
        detailScopeState.name = scope === 'manager' ? (scopeEl.dataset.tpMgr || '') : '';
        if (which === 'actual') {
            renderProgressActualModal();
            bootstrap.Modal.getOrCreateInstance(document.getElementById('progressActualModal')).show();
            return;
        }
        if (which === 'settlement') {
            renderProgressSettlementModal();
            bootstrap.Modal.getOrCreateInstance(document.getElementById('progressSettlementModal')).show();
            return;
        }
        if (which === 'target-construction' || which === 'target-settlement') {
            targetModalState.kind = which === 'target-construction' ? 'construction' : 'settlement';
            renderProgressTargetModal();
            bootstrap.Modal.getOrCreateInstance(document.getElementById('progressTargetModal')).show();
        }
    }

    // 캡션은 렌더할 때마다 innerHTML로 새로 그려지므로, 핸들러는 바뀌지 않는 부모에 한 번만 건다
    function bindProgressDetailHandlers() {
        // 상세 표의 정렬 머리글도 innerHTML 로 다시 그려지므로 바뀌지 않는 팝업 본문에 건다
        [['progressActualBody', 'actual'], ['progressSettlementBody', 'settlement'], ['progressTargetBody', 'target']]
            .forEach(([id, table]) => {
                const body = document.getElementById(id);
                if (!body) return;
                body.addEventListener('click', (e) => {
                    const th = e.target.closest('[data-tp-sort]');
                    if (th) toggleDetailSort(table, th.dataset.tpSort);
                });
                body.addEventListener('keydown', (e) => {
                    if (e.key !== 'Enter' && e.key !== ' ') return;
                    const th = e.target.closest('[data-tp-sort]');
                    if (!th) return;
                    e.preventDefault();
                    toggleDetailSort(table, th.dataset.tpSort);
                });
            });
        // 도넛 캡션과 담당자 그래프(계획외 줄 포함). 둘 다 innerHTML 로 다시 그려지므로 바뀌지 않는 부모에 건다
        ['totalProgressAmount', 'managerProgressList', 'planActualBody'].forEach((id) => {
            const host = document.getElementById(id);
            if (!host) return;
            host.addEventListener('click', (e) => {
                const el = e.target.closest('[data-tp-open]');
                if (el) openProgressDetail(el.dataset.tpOpen, el);
            });
            host.addEventListener('keydown', (e) => {
                if (e.key !== 'Enter' && e.key !== ' ') return;
                const el = e.target.closest('[data-tp-open]');
                if (!el) return;
                e.preventDefault();
                openProgressDetail(el.dataset.tpOpen, el);
            });
        });
    }

    // 시공 목표 총액(천원). 행이 없거나 아직 못 받았으면 null — 0 으로 돌려주면 '목표 0원'과 구분이 안 된다.
    function getConstructionTargetThousand() {
        const t = totalProgressState.targets;
        if (!t || !t.construction.rows.length) return null;
        return t.construction.totalThousand;
    }

    // null 이면 도넛을 '목표 미등록'으로 그린다. ERP 시공 실적은 있는데 목표가 없는 달에
    // ERP 장애용 수동 공정률로 대신 채우면, 아무 관계없는 숫자가 아무 티 없이 도넛이 된다.
    // 안쪽 링(정산 / 정산 목표). 상태를 나눠 돌려준다 — 넷은 화면에서 서로 다른 말로 보여야 한다.
    //   hidden   : 대체값 화면(ERP 시공 실적 없음) — 정산 자체를 안 받았다
    //   nodata   : 정산 행 또는 목표를 불러오지 못함 → '-'
    //   notarget : 정산 목표 행이 0개 → '미등록'
    //   ok       : value 에 % (시공과 같이 0~100 으로 자른다)
    function getSettlementPercent() {
        if (!totalProgressState.settlementEnabled) return { state: 'hidden' };
        const s = totalProgressState.settlement;
        const t = totalProgressState.targets;
        if (!s || !t) return { state: 'nodata' };
        if (!t.settlement.rows.length) return { state: 'notarget' };
        // 100%에서 자르지 않는다 — 계획을 얼마나 넘겼는지가 다음 달 계획을 고치는 근거다(링은 100%에서 가득 찬다)
        const value = Math.max(0, Math.round((s.totalThousand / t.settlement.totalThousand) * 1000) / 10);
        return { state: 'ok', value };
    }

    function getTotalProgressPercent() {
        // 지난 달 로딩·실패 중엔 숫자가 없다 — 아래 대체값 분기(수동 공정률)로 떨어지지 않게 먼저 막는다
        if (monthNavState.loading || monthNavState.actualError) return null;
        if (!totalProgressState.actualFromErp) {
            return Math.max(0, Math.min(100, Number(totalProgressState.totalProgress) || 0));
        }
        const actual = Number(totalProgressState.actualAmountThousand);
        const target = getConstructionTargetThousand();
        if (target === null || !Number.isFinite(actual)) return null;
        // 정산과 같은 이유로 100%에서 자르지 않는다. ERP 장애용 수동 공정률(위)은 사람이 넣는 값이라 0~100 그대로 둔다
        return Math.max(0, Math.round((actual / target) * 1000) / 10);
    }

    // 'YYYY-MM' 을 delta 달만큼 옮긴다. Date 를 쓰지 않는다 — 기기 시간대에 따라 달력이 바뀌는 자리를 만들지 않으려고
    function shiftMonth(ym, delta) {
        const idx = Number(ym.slice(0, 4)) * 12 + (Number(ym.slice(5, 7)) - 1) + delta;
        return `${Math.floor(idx / 12)}-${String((idx % 12) + 1).padStart(2, '0')}`;
    }

    // 지금 화면이 보여주는 달. 'YYYY-MM' 끼리는 문자열 비교가 곧 날짜 비교다
    function shownMonth() {
        return monthNavState.viewMonth || monthNavState.latestMonth;
    }

    function monthLabel(ym) {
        return `${Number(ym.slice(5, 7))}월`;
    }

    function formatKpiUpdatedAt(value) {
        const raw = String(value || '').trim();
        if (!raw) return JUN_DATA_UPDATED;
        const dt = new Date(raw);
        if (Number.isNaN(dt.getTime())) return raw;
        const yyyy = dt.getFullYear();
        const mm = String(dt.getMonth() + 1).padStart(2, '0');
        const dd = String(dt.getDate()).padStart(2, '0');
        const hh = String(dt.getHours()).padStart(2, '0');
        const min = String(dt.getMinutes()).padStart(2, '0');
        return `${yyyy}-${mm}-${dd} ${hh}:${min}`;
    }

    // 응답은 왔는데 시공 실적(split.construction)이 없을 때 쓰는 대체값 경로.
    // 60초마다 다시 부르므로, 앞선 성공이 남긴 ERP 값(시공 실적·상세·정산)을 여기서 걷어내지 않으면
    // '(ERP)' 딱지를 단 채 옛 숫자가 계속 도넛이 된다. 첫 화면과 같은 내장 대체값으로 되돌린다.
    // (fetch 자체가 실패한 경우는 기존대로 마지막으로 받은 값을 유지한다 — 일시 장애로 도넛이 흔들리지 않게)
    function resetErpMonthlyKpiToFallback() {
        totalProgressState.actualAmountThousand = JUN_TOTAL_ACTUAL_AMT;
        totalProgressState.actualFromErp = false;
        totalProgressState.actualDetailText = `(계획 ${JUN_PLAN_ACTUAL_AMT.toLocaleString('ko-KR')} + 계획외 ${JUN_EXTRA_ACTUAL_AMT.toLocaleString('ko-KR')}천원)`;
        totalProgressState.updatedAt = JUN_DATA_UPDATED;
        totalProgressState.sourceLabel = '';
        totalProgressState.breakdown = null;
        totalProgressState.settlement = null;
        totalProgressState.settlementEnabled = false;
        totalProgressState.erpMonth = '';
        totalProgressState.periodFrom = '';
        totalProgressState.periodTo = '';
    }

    // ‹ › 를 누른 직후. 옛 달의 숫자·목표를 새 달 제목 아래 남기지 않는다 — 표·도넛·캡션이 모두 '…'/'-'가 된다
    function showMonthLoading(month) {
        monthNavState.loading = true;
        monthNavState.actualError = false;
        totalProgressState.label = monthLabel(month);
        totalProgressState.erpMonth = month;
        totalProgressState.periodFrom = '';
        totalProgressState.periodTo = '';
        totalProgressState.actualAmountThousand = null;
        totalProgressState.actualFromErp = true;
        totalProgressState.actualDetailText = '';
        totalProgressState.updatedAt = '';
        totalProgressState.sourceLabel = '';
        totalProgressState.breakdown = null;
        totalProgressState.settlement = null;
        totalProgressState.settlementEnabled = true;
        totalProgressState.targets = null;
        targetsMonth = '';
    }

    // 지난 달 응답 { status, month, split } 적용. 요청한 달과 다르거나 시공 실적이 없으면 false(→ 실패로 그림)
    function applyErpMonthSplit(data, month) {
        if (!data || data.month !== month) return false;
        const split = data.split && typeof data.split === 'object' ? data.split : null;
        if (!split || split.month !== month) return false;
        const construction = normalizeBreakdown(split.construction);
        if (!construction) return false;
        monthNavState.actualError = false;
        totalProgressState.erpMonth = month;
        totalProgressState.periodFrom = toDateStrings([split.from])[0] || '';
        totalProgressState.periodTo = toDateStrings([split.to])[0] || '';
        totalProgressState.label = monthLabel(month);
        totalProgressState.actualAmountThousand = construction.totalThousand;
        totalProgressState.actualFromErp = true;
        totalProgressState.actualDetailText = '';
        // month 응답엔 updatedAt 이 없다. 비워 두면 formatKpiUpdatedAt 이 대체값 날짜(2026-06-18)를 찍으므로 받은 시각을 적는다
        // (기존 최신화 표기와 같은 브라우저 시계 — 국내 상황판 가정)
        totalProgressState.updatedAt = formatKpiUpdatedAt(new Date().toISOString());
        totalProgressState.sourceLabel = '(ERP)';
        totalProgressState.breakdown = construction;
        totalProgressState.settlement = normalizeSettlement(split.settlement);
        totalProgressState.settlementEnabled = true;
        return true;
    }

    // 지난 달 실적을 못 받음. 대체값 경로(resetErpMonthlyKpiToFallback)로 보내지 않는다 —
    // 그 경로는 6월 숫자를 그리므로 '9월' 제목 아래 6월 실적이 에러 없이 찍힌다. 실적 칸은 '못 불러옴', 목표는 그대로 보인다.
    function markErpMonthFailed(month) {
        showMonthLoading(month);
        monthNavState.loading = false;
        monthNavState.actualError = true;
    }

    function applyErpMonthlyKpi(data) {
        if (!data || typeof data !== 'object') return false;
        const split = data.split && typeof data.split === 'object' ? data.split : null;
        // 도넛의 분자는 시공 실적이다 — 월간 목표가 시공분만이라 준공 보정이 섞인 monthlyRevenue 와는 기준이 다르다.
        // split.construction 이 없으면(옛 ERP·합계 불일치) monthlyRevenue 로 대신 채우지 않는다:
        // 틀린 정의의 숫자가 화면에서 아무 티 없이 도넛이 되기 때문이다. ERP 실패와 같은 대체값 경로로 보낸다.
        const construction = normalizeBreakdown(split && split.construction);
        if (!construction) return false;

        // split.month 는 금요일 기준 주차의 달이다. data.label 은 달력 월(ERP 홈 KPI용)이라 9/28~30 엔 한 달 어긋난다 —
        // split.month 가 있으면 제목도 그 달로 쓴다(그 달 목표를 불러오면 관리자가 정한 라벨로 다시 덮인다)
        const month = /^\d{4}-(0[1-9]|1[0-2])$/.test(String(split.month || '')) ? split.month : '';
        totalProgressState.erpMonth = month;
        totalProgressState.periodFrom = month ? toDateStrings([split.from])[0] || '' : '';
        totalProgressState.periodTo = month ? toDateStrings([split.to])[0] || '' : '';
        totalProgressState.label = month
            ? `${Number(month.slice(5, 7))}월`
            : String(data.label || totalProgressState.label || '6월').trim();
        totalProgressState.actualAmountThousand = construction.totalThousand;
        totalProgressState.actualFromErp = true;
        totalProgressState.actualDetailText = '';
        totalProgressState.updatedAt = formatKpiUpdatedAt(data.updatedAt);
        totalProgressState.sourceLabel = '(ERP)';
        totalProgressState.breakdown = construction;
        totalProgressState.settlement = normalizeSettlement(split.settlement);
        totalProgressState.settlementEnabled = true;
        return true;
    }

    function toDayNumbers(value) {
        if (!Array.isArray(value)) return [];
        return value.map(Number).filter((d) => Number.isInteger(d) && d >= 1 && d <= 31);
    }

    // 'YYYY-MM-DD' 모양만 남긴다 — 화면(innerHTML)에 찍히는 값이라 태그가 될 문자열이 들어올 자리를 남기지 않는다
    function toDateStrings(value) {
        if (!Array.isArray(value)) return [];
        return value.map((v) => String(v || '')).filter((s) => /^\d{4}-\d{2}-\d{2}$/.test(s));
    }

    // 서버가 이미 모양을 맞춰 보내지만, 여기서도 총액을 '행의 합'으로 다시 만든다.
    // 도넛에 찍히는 숫자와 표에 보이는 행이 같은 배열에서 나와야 둘이 갈라질 자리가 없다.
    function normalizeBreakdown(raw) {
        // 행이 0개인 것과 상세가 아예 없는 것은 다른 상황이다(전자는 '이번 달 실적 없음',
        // 후자는 '못 불러옴') — 여기서 뭉개면 화면이 둘을 같은 말로 설명하게 된다.
        if (!raw || !Array.isArray(raw.rows)) return null;
        const rows = raw.rows.map((r) => ({
            jijungNo: String(r.jijungNo || ''),
            name: String(r.name || ''),
            amountThousand: Number(r.amountThousand) || 0,
            // 아래에서 innerHTML로 들어가는 값이라 여기서 숫자로 못 박는다.
            // 서버(app/api/erp.py)가 이미 1~31 정수로 걸러 보내지만, 태그로 해석될 수 있는
            // 문자열이 이 경로로 들어올 자리를 아예 남기지 않는다.
            days: toDayNumbers(r.days),
            nightDays: toDayNumbers(r.nightDays),
            // 주차 기간은 달을 넘나든다 — 어느 달의 31일인지 그리려면 전체 날짜가 필요하다(옛 ERP면 빈 배열 → days 로 그림)
            dates: toDateStrings(r.dates),
            nightDates: toDateStrings(r.nightDates),
            // 시공 담당별(ERP 공사이력.담당공무_id). null = 옛 ERP 이거나 합이 안 맞아 중계가 버린 행 → 옛 규칙으로 나눈다
            managers: Array.isArray(r.managers)
                ? r.managers.map((m) => ({
                    name: String(m.name || ''),
                    amountThousand: Number(m.amountThousand) || 0,
                    dates: toDateStrings(m.dates),
                    nightDates: toDateStrings(m.nightDates),
                }))
                : null,
        }));
        return { rows, totalThousand: rows.reduce((sum, r) => sum + r.amountThousand, 0) };
    }

    // 정산(끊은 계산서) 행. 총액은 여기서도 '행의 합'으로 다시 만든다 — 캡션 숫자와 팝업 합계가 같은 배열에서 나오게.
    function normalizeSettlement(raw) {
        // 0건('이번 달 계산서 없음')과 상세 없음('못 불러옴')을 구분한다 — normalizeBreakdown 과 같은 이유
        if (!raw || !Array.isArray(raw.rows)) return null;
        const rows = raw.rows.filter((r) => r && typeof r === 'object').map((r) => {
            const day = toDayNumbers([r.day]);
            return {
                jijungNo: String(r.jijungNo || ''),
                name: String(r.name || ''),
                kind: String(r.kind || ''),
                // innerHTML 로 들어가는 값이라 숫자로 못 박는다(서버가 이미 걸렀어도 자리를 남기지 않는다)
                day: day.length ? day[0] : null,
                date: toDateStrings([r.date])[0] || '',
                amountThousand: Number(r.amountThousand) || 0,
                // 정산 담당(ERP 수주.정산담당자_id). '' = 정산 미지정, null = 옛 ERP → 옛 규칙(목표 행 → 계획외 지정)
                manager: typeof r.manager === 'string' ? r.manager : null,
            };
        });
        return { rows, totalThousand: rows.reduce((sum, r) => sum + r.amountThousand, 0) };
    }

    function applyMonthlyProgressConfig(data) {
        const cfg = data && data.data ? data.data : data;
        if (!cfg || typeof cfg !== 'object') return false;
        const progress = Number(cfg.total_progress);
        if (cfg.label) totalProgressState.label = String(cfg.label).trim();
        if (Number.isFinite(progress)) totalProgressState.totalProgress = progress;
        totalProgressState.targets = normalizeTargets(cfg.targets);
        if (Array.isArray(cfg.managers)) totalProgressState.managers = cfg.managers.map((m) => String(m || '').trim()).filter(Boolean);
        if (Array.isArray(cfg.unplannedAssignments)) {
            totalProgressState.unplannedOwner = new Map(cfg.unplannedAssignments
                .filter((a) => a && typeof a === 'object')
                .map((a) => [String(a.jijungNo || '').trim(), String(a.manager || '').trim()])
                .filter(([no, m]) => no && m));
        }
        return true;
    }

    // 목표 행. 서버는 총액을 보내지 않는다 — 여기서 '행의 합'으로 만들어 도넛 분모와 팝업 합계가 같은 배열에서 나오게 한다.
    function normalizeTargets(raw) {
        // targets 가 없는 응답(옛 서버)은 '행 0개'가 아니라 '못 받음'이다 — 목표 미등록으로 말하면 없는 사실을 말하는 것
        if (!raw || typeof raw !== 'object') return null;
        const one = (list) => {
            const rows = (Array.isArray(list) ? list : [])
                .filter((r) => r && typeof r === 'object')
                .map((r) => ({
                    jijungNo: String(r.jijungNo || ''),
                    name: String(r.name || ''),
                    amountThousand: Number(r.amountThousand) || 0,
                    manager: String(r.manager || '').trim(),
                }));
            return { rows, totalThousand: rows.reduce((sum, r) => sum + r.amountThousand, 0) };
        };
        return { construction: one(raw.construction), settlement: one(raw.settlement) };
    }

    // 담당자별 진척(한 종류: 시공 또는 정산).
    //   목표           = 그 담당자 목표 행의 합
    //   실적           = 목표 행의 공사(지중No) 실적 + 관리자가 그 담당자에게 지정한 계획외 공사 실적 → % 는 이것 / 목표
    //                    (2026-10-13 요청: '+ 계획외'를 따로 적으니 금액이 눈에 안 들어온다 → 실적에 합침.
    //                     대가: %가 '계획을 얼마나 지켰나'가 아니라 '목표 대비 얼마나 일했나'가 된다)
    //   계획외(남은 것) = 담당도 목표도 없는 실적 → unplannedThousand, '계획외 실적' 줄 (붙일 담당자가 없어 따로 남긴다)
    //   ⚠️ 시공 실적은 예외(2026-10-29): 행에 managers(ERP 공사이력.담당공무_id 로 나눈 몫)가 있으면 그 담당 칸으로만 간다.
    //      목표 행 담당·계획외 지정은 보지 않는다 — 시공 담당은 ERP 한 곳에서 정해야 공무 화면과 숫자가 같다.
    //      목표 행 담당과 ERP 담당이 다르면 목표는 목표 행 담당에, 실적은 ERP 담당에 붙는다(%가 낮게 보이는 쪽이 목표 행을 고칠 신호).
    //      그래서 계획외 지정(공사 하나에 한 명)은 사실상 정산 전용이다 — 시공·정산을 한 명에게 묶으면 정산 담당에게 시공이 딸려갔다.
    //   ⚠️ 정산 실적도 같다: 행에 manager(ERP 수주.정산담당자_id)가 있으면 그 칸으로만 간다. 둘 다 오면 이 화면은 담당을 판단하지 않고
    //      ERP 가 정한 대로 그리기만 한다 — 아래 '목표 행 → 계획외 지정' 규칙은 옛 ERP 응답(담당 칸 없음)을 위한 것이다.
    //   ('' 칸 = 담당 칸이 생기기 전에 넣은 옛 미지정 행. 새 행은 담당 없이 못 들어온다)
    // 어느 실적 행도 버리지 않으므로 '담당자 칸들 + 계획외 실적' = actual.totalThousand(도넛 캡션 숫자)다.
    // actual 이 null(못 받음)이면 실적은 null 로 둔다 — 0 으로 두면 '이번 달 실적 0'과 구분이 안 된다.
    // 칸마다 금액뿐 아니라 그 금액을 만든 행 목록(targetRows·actualRows)도 담는다 — 담당자별 상세 팝업은 이 목록을 그대로 그린다.
    // 금액은 목록의 합으로만 만들므로 '막대 숫자 = 팝업 합계'가 계산이 아니라 구조로 보장된다(규칙이 이 함수 하나에만 산다).
    function buildManagerProgress(target, actual, unplannedOwner) {
        const ownerByNo = new Map(target.rows.map((r) => [r.jijungNo, r.manager]));
        const buckets = new Map();
        const bucket = (name) => {
            if (!buckets.has(name)) buckets.set(name, { targetRows: [], actualRows: [] });
            return buckets.get(name);
        };
        target.rows.forEach((r) => { bucket(r.manager).targetRows.push(r); });
        const unplannedRows = [];
        if (actual) {
            actual.rows.forEach((r) => {
                if (Array.isArray(r.managers)) {
                    // 몫마다 그 담당의 금액·날짜만 담은 행으로 쪼갠다 — 담당자 상세 팝업이 이 행을 그대로 그린다. '' = 담당 미지정 칸
                    r.managers.forEach((m) => {
                        bucket(m.name).actualRows.push({ ...r, amountThousand: m.amountThousand, dates: m.dates, nightDates: m.nightDates, days: [], nightDays: [] });
                    });
                    return;
                }
                if (typeof r.manager === 'string') {
                    // 정산 행: 그 공사의 정산 담당 칸으로만 간다('' = 담당 미지정 칸)
                    bucket(r.manager).actualRows.push(r);
                    return;
                }
                // 목표 행이 우선이다 — 같은 공사가 목표에도 있고 계획외 지정에도 남아 있으면 계획분으로만 센다(두 번 세지 않게)
                if (ownerByNo.has(r.jijungNo)) bucket(ownerByNo.get(r.jijungNo)).actualRows.push(r);
                else if (unplannedOwner.has(r.jijungNo)) bucket(unplannedOwner.get(r.jijungNo)).actualRows.push(r);
                else unplannedRows.push(r);
            });
        }
        buckets.forEach((b) => {
            b.targetThousand = sumThousand(b.targetRows);
            b.actualThousand = actual ? sumThousand(b.actualRows) : null;
        });
        return { buckets, unplannedRows, unplannedThousand: actual ? sumThousand(unplannedRows) : null };
    }

    function sumThousand(rows) {
        return rows.reduce((sum, r) => sum + r.amountThousand, 0);
    }

    // 한 종류(시공/정산)의 담당자별 진척. 그래프와 상세 팝업이 둘 다 이 호출을 거친다 — 입력(실적 원본)이 갈리지 않게.
    // 대체값 화면(ERP 시공 실적 없음)에선 breakdown 이 null, 정산을 안 받는 화면에선 정산 실적이 null 이다.
    function getManagerProgress(kind) {
        const t = totalProgressState.targets;
        if (!t) return null;
        const actual = kind === 'construction'
            ? totalProgressState.breakdown
            : (totalProgressState.settlementEnabled ? totalProgressState.settlement : null);
        return buildManagerProgress(t[kind], actual, totalProgressState.unplannedOwner);
    }

    // 받아오기만 한다(적용은 loadTotalProgressHome 이 순번을 확인한 뒤). 실패는 { ok:false } — 400 과 503 을 화면에선 같은 '못 불러옴'으로 그린다
    async function fetchJson(url) {
        try {
            const res = await fetch(url);
            if (!res.ok) return { ok: false, status: res.status };
            return { ok: true, data: await res.json() };
        } catch (_e) {
            return { ok: false, status: 0 };
        }
    }

    // 목표는 화면이 보는 달(ERP 금요일 기준 달)로 부른다 — 서버의 달력 월로 부르면 9/28~30 에 10월 실적 / 9월 목표가 된다.
    // month 가 비면(옛 ERP·대체값) 서버 기본(달력 월)으로 부른다.
    function monthlyProgressConfigUrl(month) {
        return month ? `${MONTHLY_PROGRESS_CONFIG_API}?month=${encodeURIComponent(month)}` : MONTHLY_PROGRESS_CONFIG_API;
    }

    // 실적을 먼저 받아 달을 정하고, 그 달의 목표를 받은 뒤 한 번만 그린다(새 달 실적 / 옛 달 목표가 잠깐 그려지지 않게).
    // 60초 갱신과 ‹ › 가 같은 함수를 부른다 — 늦게 끝난 쪽이 먼저 시작한 쪽 결과를 덮지 않게 순번으로 거른다.
    async function loadTotalProgressHome() {
        const seq = ++totalProgressLoadSeq;
        // 5분 복귀로 이번 달 화면이 됐는데 아래 ①이 실패하면, 화면엔 아직 지난 달 숫자(또는 지난 달 실패 상태)가 남아 있다 → 그것도 실패로 그린다
        let leftPast = false;
        if (monthNavState.viewMonth && Date.now() - monthNavState.viewSince >= VIEW_RETURN_MS) {
            monthNavState.viewMonth = '';
            monthNavState.actualError = false;
            leftPast = true;
        }

        // ① 이번 달(month 없음) — 오른쪽 끝을 알려면 지난 달을 보는 중에도 항상 부른다
        const current = await fetchJson(ERP_MONTHLY_KPI_API);
        if (seq !== totalProgressLoadSeq) return;
        if (current.ok) {
            const split = current.data && current.data.split;
            // 시공 칸을 못 쓰는 응답의 달은 받지 않는다 — 마지막으로 알던 오른쪽 끝을 유지해 ‹ › 는 계속 동작한다
            const usable = split && normalizeBreakdown(split.construction) !== null;
            const latest = usable && MONTH_RE.test(String(split.month || '')) ? split.month : '';
            if (latest) {
                monthNavState.latestMonth = latest;
                // 금주 달이 넘어가 보던 달과 같아졌으면 이번 달 화면으로 친다
                if (monthNavState.viewMonth && monthNavState.viewMonth >= latest) monthNavState.viewMonth = '';
            }
        }

        const viewing = monthNavState.viewMonth;
        if (!viewing) {
            // '마지막 값'이 이번 달의 진짜 값이 아닌 경우: ›직후(로딩), 직전에도 실패(연속 실패), 지난 달에서 복귀
            const wasBlank = monthNavState.loading || monthNavState.actualError || leftPast;
            monthNavState.loading = false;
            monthNavState.actualError = false;
            // 비워지지 않은 화면은 기존 동작 그대로: 응답은 왔는데 시공 실적이 없으면 대체값, fetch 실패면 마지막 값 유지(백로그 B안 범위)
            if (current.ok) {
                if (!applyErpMonthlyKpi(current.data)) {
                    // 비워진 화면(복귀·로딩·연속 실패)에선 대체값 경로가 label 을 되돌리지 않아 지난 달 제목 아래 6월 숫자가 찍힌다 → 실패로 그린다
                    if (wasBlank) markErpMonthFailed(monthNavState.latestMonth || totalProgressState.erpMonth);
                    else resetErpMonthlyKpiToFallback();
                }
            } else if (wasBlank) {
                // › 로 이번 달에 돌아온 직후 실패 — showMonthLoading 이 '마지막 값'을 이미 비웠다.
                // 그대로 두면 actualAmountThousand=null 이 캡션에서 '시공 0'으로 찍히므로 실패로 그린다.
                // 달은 latestMonth — 5분 복귀면 erpMonth 는 아직 지난 달이다
                markErpMonthFailed(monthNavState.latestMonth || totalProgressState.erpMonth);
            }
        } else {
            // ② 지난 달(month 경로)
            const past = await fetchJson(`${ERP_MONTHLY_KPI_API}?month=${encodeURIComponent(viewing)}`);
            if (seq !== totalProgressLoadSeq) return;
            monthNavState.loading = false;
            if (!past.ok || !applyErpMonthSplit(past.data, viewing)) markErpMonthFailed(viewing);
        }

        // ③ 그 달의 목표
        const month = totalProgressState.erpMonth;
        const cfg = await fetchJson(monthlyProgressConfigUrl(month));
        if (seq !== totalProgressLoadSeq) return;
        if (cfg.ok && applyMonthlyProgressConfig(cfg.data)) {
            targetsMonth = month;
        } else if (targetsMonth !== month) {
            // 같은 달이면 마지막 목표를 유지(일시 장애로 흔들리지 않게), 다른 달이면 비운다 — 다른 달 계획을 이 달 계획으로 그리지 않게
            totalProgressState.targets = null;
        }
        renderTotalProgressChartHome();
    }

    // ‹ › 한 칸. 범위 밖이면 아무것도 안 한다(버튼도 막혀 있다)
    function goPlanActualMonth(delta) {
        const base = shownMonth();
        if (!base || !monthNavState.latestMonth) return;
        const next = shiftMonth(base, delta);
        if (next < MIN_PLAN_MONTH || next > monthNavState.latestMonth) return;
        monthNavState.viewMonth = next === monthNavState.latestMonth ? '' : next;
        monthNavState.viewSince = Date.now();
        showMonthLoading(next);
        renderTotalProgressChartHome();
        loadTotalProgressHome();
    }

    // ═══════════════════════════ 현장 날씨 ═══════════════════════════

    const WEATHER_ICONS = { clear: '☀️', cloudy: '⛅', overcast: '☁️', rain: '🌧️', snow: '❄️', shower: '🌦️' };

    function renderWeather(w) {
        const setText = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
        setText('weatherCity', w.city || '안양');
        setText('weatherIcon', WEATHER_ICONS[w.icon] || '⛅');
        setText('weatherTemp', (w.temp != null ? `${w.temp}°` : '--°'));
        setText('weatherCond', w.condition || '-');
        setText('weatherPop', (w.pop != null ? `${w.pop}%` : '--'));
        setText('weatherWind', (w.wind != null ? `${w.wind}m/s` : '--'));
        setText('weatherHumidity', (w.humidity != null ? `${w.humidity}%` : '--'));

        const fc = document.getElementById('weatherForecast');
        if (fc) {
            const days = Array.isArray(w.forecast) ? w.forecast.slice(0, 4) : [];
            fc.innerHTML = days.map((d) => (
                `<div class="wf-day">` +
                `<div class="d">${escapeHtml(d.day || '-')}</div>` +
                `<div class="i">${WEATHER_ICONS[d.icon] || '⛅'}</div>` +
                `<div class="t">${d.high != null ? d.high + '°' : '--'}<small> / ${d.low != null ? d.low + '°' : '--'}</small></div>` +
                `</div>`
            )).join('');
        }

        const alertEl = document.getElementById('weatherAlert');
        if (alertEl) alertEl.textContent = w.alert || '';
    }

    function renderWeatherPlaceholder() {
        const setText = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
        setText('weatherTemp', '--°');
        setText('weatherCond', '현장 날씨 API 연동 후 표시됩니다');
        setText('weatherPop', '--');
        setText('weatherWind', '--');
        setText('weatherHumidity', '--');
        const fc = document.getElementById('weatherForecast');
        if (fc) {
            fc.innerHTML = ['', '', '', ''].map(() => (
                `<div class="wf-day"><div class="d">-</div><div class="i">⛅</div><div class="t">--<small> / --</small></div></div>`
            )).join('');
        }
        const alertEl = document.getElementById('weatherAlert');
        if (alertEl) alertEl.textContent = '';
    }

    async function loadWeatherHome() {
        try {
            const res = await fetch(WEATHER_API_BASE);
            if (!res.ok) throw new Error('weather unavailable');
            const data = await res.json();
            renderWeather(data);
        } catch (_e) {
            renderWeatherPlaceholder();
        }
    }

    // ═══════════════════════════ 바로가기 ═══════════════════════════

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
            const normalized = rows.slice(0, 12).map((row) => ({
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
        bindProgressDetailHandlers();
        const paPrev = document.getElementById('planActualPrev');
        const paNext = document.getElementById('planActualNext');
        if (paPrev) paPrev.addEventListener('click', () => goPlanActualMonth(-1));
        if (paNext) paNext.addEventListener('click', () => goPlanActualMonth(1));
        const ok = await ensureSession();
        if (!ok) return;
        updateNowLabel();
        await fetchMeAndPaint();
        renderTotalProgressChartHome();
        loadTotalProgressHome();
        renderWeatherPlaceholder();
        await Promise.all([loadFrequentSitesHome(), loadWeatherHome()]);
        setInterval(() => {
            updateNowLabel();
            loadTotalProgressHome();
            loadFrequentSitesHome();
            loadWeatherHome();
        }, 60000);
    }

    window.loadFrequentSitesHome = loadFrequentSitesHome;

    window.addEventListener('load', initializeHomePage);
})();
