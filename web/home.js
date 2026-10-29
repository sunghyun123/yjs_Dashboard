(function () {
    // ═══════════════════════════════════════════════════════════════════════
    //  연동 키 (사용자 발급 후 입력) ─ 이 두 값만 채우면 지도/날씨가 동작합니다.
    // ───────────────────────────────────────────────────────────────────────
    //  카카오맵 JS 키는 서버 .env(KAKAO_MAP_JS_KEY)에 두고 `/api/public-config`로 받아온다.
    //    (도메인 제한이 걸린 공개 키이지만 코드/깃에 하드코딩하지 않기 위함)
    //  WEATHER_API_BASE: 날씨는 CORS/키 보호를 위해 백엔드 프록시(`/api/weather/current`) 경유.
    //    백엔드 엔드포인트가 준비되면 자동으로 실데이터가 표시됩니다.
    const WEATHER_API_BASE = '/api/weather/current';
    const ERP_MONTHLY_KPI_API = '/api/erp/monthly-kpi';
    const ERP_MATERIALS_API = '/api/erp/materials';
    const MONTHLY_PROGRESS_CONFIG_API = '/api/erp/monthly-progress-config';
    let kakaoMapJsKey = ''; // /api/public-config에서 런타임 주입
    // ═══════════════════════════════════════════════════════════════════════

    // ─── 지도 핀 데이터 소스 ────────────────────────────────────────────────
    // 서버 `/api/progress-sites`(data/progress_sites.json)에서 받아온다.
    // 위치는 다음 우선순위로 결정: ① lat/lng(관리 페이지에서 핀 고정) → ② addr(주소 지오코딩)
    //   → ③ 공사명에서 자동 추출(폴백). 관리 화면: /map-admin.html
    let MONTHLY_PROGRESS_DATA = [];

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
    const targetModalState = { kind: 'construction' };
    // 상세 팝업 셋이 지금 누구 몫을 보여주는지. type: 'all'(도넛 캡션) | 'manager'(담당자 줄, name) | 'unplanned'(계획외 실적 줄)
    const detailScopeState = { type: 'all', name: '' };
    // ─────────────────────────────────────────────────────────────────────────

    // 담당자별 핀 색상/약칭 (메모리 project-home-renewal 확정값)
    const MANAGER_STYLE = {
        '김무선': { color: '#2f6fed', short: '무선' },
        '김상훈': { color: '#e8590c', short: '상훈' },
        '이재규': { color: '#2f9e44', short: '이재' },
        '김단후': { color: '#ae3ec9', short: '단후' },
    };
    const DEFAULT_MANAGER_STYLE = { color: '#64748b', short: '담당' };
    // 담당자별 진척 그래프에서 MANAGER_STYLE 에 없는 담당자에게 주는 예비 색
    const EXTRA_MANAGER_COLORS = ['#0ca678', '#f08c00', '#1098ad', '#d6336c', '#5c7cfa', '#868e96'];

    // 안양시청 부근 — 키워드 검색 위치 보정 / 지도 초기 중심
    const ANYANG_CENTER = { lat: 37.3943, lng: 126.9568 };
    const GEO_CACHE_KEY = 'yjs_geo_cache_v1';

    let workerReturnTimeModal = null;
    let workerReturnTimeTargetUser = '';
    let mapInstance = null;
    let activeTooltipOverlay = null;

    function managerStyle(name) {
        return MANAGER_STYLE[String(name || '').trim()] || DEFAULT_MANAGER_STYLE;
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
        const noTargetText = totalProgressState.targets ? '미등록' : '-';
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
            listEl.innerHTML = '<div class="text-muted small">목표를 불러오지 못했습니다.</div>';
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
        ['totalProgressAmount', 'managerProgressList'].forEach((id) => {
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
        if (!totalProgressState.actualFromErp) {
            return Math.max(0, Math.min(100, Number(totalProgressState.totalProgress) || 0));
        }
        const actual = Number(totalProgressState.actualAmountThousand);
        const target = getConstructionTargetThousand();
        if (target === null || !Number.isFinite(actual)) return null;
        // 정산과 같은 이유로 100%에서 자르지 않는다. ERP 장애용 수동 공정률(위)은 사람이 넣는 값이라 0~100 그대로 둔다
        return Math.max(0, Math.round((actual / target) * 1000) / 10);
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

    // 목표는 ERP 가 정한 달(금요일 기준 주차의 달)로 부른다 — 서버의 달력 월로 부르면 9/28~30 에 10월 실적 / 9월 목표가 된다.
    // erpMonth 가 비면(옛 ERP·대체값) 서버 기본(달력 월)으로 부른다.
    async function loadMonthlyProgressConfigHome() {
        try {
            const month = totalProgressState.erpMonth;
            const url = month ? `${MONTHLY_PROGRESS_CONFIG_API}?month=${encodeURIComponent(month)}` : MONTHLY_PROGRESS_CONFIG_API;
            const res = await fetch(url);
            if (!res.ok) throw new Error('monthly progress config unavailable');
            applyMonthlyProgressConfig(await res.json());
        } catch (_e) {
            // Keep built-in fallback config.
        }
    }

    async function loadErpMonthlyKpiHome() {
        try {
            const res = await fetch(ERP_MONTHLY_KPI_API);
            if (!res.ok) throw new Error('ERP monthly KPI unavailable');
            const data = await res.json();
            // 응답은 왔지만 시공 실적이 없으면 앞선 성공의 잔재를 걷어내고 대체값으로 다시 그린다
            if (!applyErpMonthlyKpi(data)) resetErpMonthlyKpiToFallback();
        } catch (_e) {
            // Keep the initial hardcoded fallback when ERP is unavailable.
        }
    }

    // 실적을 먼저 받아 달을 정하고, 그 달의 목표를 받은 뒤 한 번만 그린다.
    // 둘을 따로 그리면 달이 바뀌는 순간 '새 달 실적 / 옛 달 목표'인 도넛이 잠깐 그려진다.
    async function loadTotalProgressHome() {
        await loadErpMonthlyKpiHome();
        await loadMonthlyProgressConfigHome();
        renderTotalProgressChartHome();
    }

    // ═══════════════════════════ 자재 현황 (ERP 실시간) ═══════════════════════════
    // 계약: /api/erp/materials → { cable:{stats, groups[]}, etc:{groups[]}, updatedAt }
    // 재고 타일은 stats(창고 실재고, 출고중 제외)를 그대로 쓴다. lines/chips는 출고중 포함이라
    // 타일과 합이 다를 수 있음(ERP가 명시한 의도된 차이) — lines에서 재집계하지 않는다.
    let materialsEverLoaded = false;

    function matStatTile(label, value, unit) {
        return `<div class="cable-stat"><div class="lb">${label}</div>` +
            `<div class="v">${Number(value || 0).toLocaleString('ko-KR')}<small>${unit}</small></div></div>`;
    }

    function matCableChip(chip) {
        // 잔재(창고 복귀 잔여) / 출고중(현재 반출)은 배타적 상태 — 각자 다른 태그
        const tag = chip.remnant ? '<span class="rtag">잔재</span>'
            : chip.shipping ? '<span class="stag">출고중</span>' : '';
        const cls = 'cable-chip' + (chip.remnant ? ' rem' : chip.shipping ? ' shipping' : '');
        const maker = chip.maker ? escapeHtml(chip.maker) : '';
        return `<span class="${cls}"><b>${Number(chip.remaining || 0).toLocaleString('ko-KR')}m ×${Number(chip.count || 0)}</b>${maker}${tag}</span>`;
    }

    function matCableBars(chip) {
        // 칩 하나 = 드럼 count개 → 막대 count개, 길이 --w = 남은 미터수
        const cls = chip.remnant ? ' class="rem"' : chip.shipping ? ' class="shipping"' : '';
        const w = Number(chip.remaining || 0);
        const n = Number(chip.count || 0);
        let out = '';
        for (let i = 0; i < n; i++) out += `<span style="--w:${w}"${cls}></span>`;
        return out;
    }

    function matCableLine(line, isLv) {
        const chips = Array.isArray(line.chips) ? line.chips : [];
        // "잔재만 남음" = 이 선종의 남은 드럼이 전부 잔재일 때(대시보드가 chips로 자체 판정)
        const allRemnant = chips.length > 0 && chips.every((c) => c.remnant);
        const flag = allRemnant ? '<span class="cable-flag">잔재만 남음</span>' : '';
        return `<div class="cable-row${isLv ? ' lv' : ''}">` +
            `<div class="cable-row-top"><span class="cable-code">${escapeHtml(line.code || '')}</span>${flag}` +
            `<span class="cable-total"><b>${Number(line.totalRemaining || 0).toLocaleString('ko-KR')}m</b> · ${Number(line.drumCount || 0)}드럼</span></div>` +
            `<div class="cable-drumbar">${chips.map(matCableBars).join('')}</div>` +
            `<div class="cable-drums">${chips.map(matCableChip).join('')}</div>` +
            `</div>`;
    }

    function renderMaterials(data) {
        const statsEl = document.getElementById('matCableStats');
        const colsEl = document.getElementById('matCableCols');
        const etcEl = document.getElementById('matEtcGrid');
        const srcEl = document.getElementById('matSource');
        if (!statsEl || !colsEl || !etcEl) return;

        const cable = data.cable || {};
        const stats = cable.stats || {};
        const groups = Array.isArray(cable.groups) ? cable.groups : [];
        const etcGroups = data.etc && Array.isArray(data.etc.groups) ? data.etc.groups : [];

        statsEl.innerHTML =
            matStatTile('고압 재고', stats.highVoltageStock, 'm') +
            matStatTile('저압 재고', stats.lowVoltageStock, 'm') +
            matStatTile('잔재 드럼', stats.remnantDrums, '개');

        // 케이블: 전압 그룹 제목 + 선종 행. 저압은 lv 스타일. 순서는 ERP가 이미 정렬해 보냄.
        const hasCable = groups.some((g) => Array.isArray(g.lines) && g.lines.length);
        if (hasCable) {
            colsEl.innerHTML = groups.map((g) => {
                const lines = Array.isArray(g.lines) ? g.lines : [];
                if (!lines.length) return '';
                const isLv = g.voltage === '저압';
                const title = `<div class="cable-group-title${isLv ? ' lv' : ''}"><span class="gd"></span>${escapeHtml(g.voltage || '')}</div>`;
                return title + lines.map((l) => matCableLine(l, isLv)).join('');
            }).join('');
        } else {
            colsEl.innerHTML = '<div class="text-muted small" style="padding:12px 2px;">케이블 재고가 없습니다.</div>';
        }

        // 기타 자재: 분류 그룹별. 수량 0 품목은 ERP가 이미 제외해서 보냄.
        if (etcGroups.length) {
            etcEl.innerHTML = etcGroups.map((grp) => {
                const items = Array.isArray(grp.items) ? grp.items : [];
                const rows = items.map((it) =>
                    `<div class="etc-row"><span class="n">${escapeHtml(it.name || '')}</span>` +
                    `<span class="c">${Number(it.count || 0).toLocaleString('ko-KR')}<small>${escapeHtml(it.unit || '')}</small></span></div>`
                ).join('');
                return `<div class="etc-group"><h3>${escapeHtml(grp.category || '')}</h3>${rows}</div>`;
            }).join('');
        } else {
            etcEl.innerHTML = '<div class="text-muted small" style="padding:12px 2px;">기타 자재 재고가 없습니다.</div>';
        }

        if (srcEl) srcEl.textContent = `ERP 실시간 · 최신화 ${formatKpiUpdatedAt(data.updatedAt)}`;
        materialsEverLoaded = true;
    }

    function setMaterialsError() {
        const colsEl = document.getElementById('matCableCols');
        const etcEl = document.getElementById('matEtcGrid');
        const srcEl = document.getElementById('matSource');
        const msg = '<div class="text-danger small" style="padding:12px 2px;">자재 데이터를 불러오지 못했습니다.</div>';
        if (colsEl) colsEl.innerHTML = msg;
        if (etcEl) etcEl.innerHTML = msg;
        if (srcEl) srcEl.textContent = 'ERP 연동 오류';
    }

    async function loadMaterialsHome() {
        try {
            const res = await fetch(ERP_MATERIALS_API);
            if (!res.ok) throw new Error('ERP materials unavailable');
            const data = await res.json();
            renderMaterials(data);
        } catch (_e) {
            // 첫 로드 실패는 정직하게 오류 표시. 이미 한 번 그렸으면 60초 갱신의
            // 일시 실패이므로 마지막 정상 데이터를 유지한다(도넛과 같은 방침).
            if (!materialsEverLoaded) setMaterialsError();
        }
    }

    // ═══════════════════════════ 진행중 공사 지도 ═══════════════════════════

    function setMapPlaceholder(text, show) {
        const ph = document.getElementById('mapPlaceholder');
        const txt = document.getElementById('mapPlaceholderText');
        if (txt && text != null) txt.textContent = text;
        if (ph) ph.classList.toggle('d-none', !show);
    }

    // 공사명 → 지오코딩 후보 쿼리(우선순위 순)
    function buildGeocodeQueries(name) {
        const raw = String(name || '')
            .replace(/_\d+\b/g, ' ')      // 끝 코드 _3206
            .replace(/\([^)]*\)/g, ' ')   // 괄호 내용
            .trim();
        const out = [];
        const seen = new Set();
        const push = (mode, query) => {
            const q = String(query || '').trim();
            if (!q || q.length < 2) return;
            const key = mode + '|' + q;
            if (seen.has(key)) return;
            seen.add(key);
            out.push({ mode, query: q });
        };

        // 1) 지번 주소: ○○동/리/가 + 번지
        const jibun = raw.match(/([가-힣]+(?:동|리|가))\s*(\d+(?:-\d+)?)/);
        if (jibun) {
            push('address', `${jibun[1]} ${jibun[2]}`);
            push('keyword', `${jibun[1]} ${jibun[2]}`);
        }

        // 2) 랜드마크 키워드: 공법/규격/용도 단어 제거 후 앞쪽 토큰
        const cleaned = raw
            .replace(/\d+(?:,\d+)?\s*k?w/gi, ' ')
            .replace(/지중화공사|지중공사|교체공사|보수공사|복구공사|설치공사|신설공사|증설공사|보강공사|정비|조성사업|전기공사/g, ' ')
            .replace(/지중케이블|노후변압기선로|지상개폐기|배전간선|불량개소|특정제원|수명만료|경과지|맨홀|관로|계통|외상고장|저압접속/g, ' ')
            .replace(/일반용|주택용|상가용|가로등|고압|저압|임시|상용|신설|증설|교체|보수|복구|설치|노후|경과|불량|지중/g, ' ')
            .replace(/[A-Za-z()㈜,·\d]/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();
        const tokens = cleaned.split(' ').filter((t) => t.length >= 2);
        if (tokens.length) {
            push('keyword', tokens.slice(0, 2).join(' '));
            push('keyword', tokens[0]);
        }

        // 3) 최후: 동 이름만으로 대략 중심
        const dong = raw.match(/[가-힣]+동/);
        if (dong) push('keyword', dong[0]);

        return out;
    }

    // 항목별 지오코딩 후보: 주소(addr)가 있으면 정확 검색을 앞에 두고, 없으면 공사명 추출
    function buildQueriesForItem(item) {
        const addr = String((item && item.addr) || '').trim();
        const out = [];
        if (addr) {
            out.push({ mode: 'address', query: addr });
            out.push({ mode: 'keyword', query: addr });
        }
        return out.concat(buildGeocodeQueries(item.name));
    }

    // 서버에서 지도 데이터(진행중 공사 목록)를 받아온다.
    async function loadProgressSites() {
        try {
            const res = await fetch('/api/progress-sites');
            if (!res.ok) return [];
            const data = await res.json();
            return Array.isArray(data.sites) ? data.sites : [];
        } catch (_e) {
            return [];
        }
    }

    function loadGeoCache() {
        try { return JSON.parse(localStorage.getItem(GEO_CACHE_KEY)) || {}; }
        catch (_e) { return {}; }
    }

    function saveGeoCache(cache) {
        try { localStorage.setItem(GEO_CACHE_KEY, JSON.stringify(cache)); }
        catch (_e) { /* 용량 초과 등 무시 */ }
    }

    // 카카오 지오코더/장소검색을 순차 시도해 첫 성공 좌표 반환
    function geocodeQueries(geocoder, places, queries, centerLatLng) {
        return new Promise((resolve) => {
            let idx = 0;
            const tryNext = () => {
                if (idx >= queries.length) { resolve(null); return; }
                const { mode, query } = queries[idx++];
                if (mode === 'address') {
                    geocoder.addressSearch(query, (res, status) => {
                        if (status === kakao.maps.services.Status.OK && res && res[0]) {
                            resolve({ lat: Number(res[0].y), lng: Number(res[0].x) });
                        } else { tryNext(); }
                    });
                } else {
                    places.keywordSearch(query, (res, status) => {
                        if (status === kakao.maps.services.Status.OK && res && res[0]) {
                            resolve({ lat: Number(res[0].y), lng: Number(res[0].x) });
                        } else { tryNext(); }
                    }, { location: centerLatLng, radius: 20000 });
                }
            };
            tryNext();
        });
    }

    function pinImageSrc(style) {
        const svg =
            `<svg xmlns='http://www.w3.org/2000/svg' width='40' height='48' viewBox='0 0 40 48'>` +
            `<path d='M20 47C20 47 36 28 36 16.5A16 16 0 1 0 4 16.5C4 28 20 47 20 47Z' fill='${style.color}' stroke='#ffffff' stroke-width='2.5'/>` +
            `<text x='20' y='21' text-anchor='middle' font-family='Malgun Gothic,AppleSDGothicNeo,sans-serif' font-size='11' font-weight='700' fill='#ffffff'>${style.short}</text>` +
            `</svg>`;
        return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
    }

    function closeActiveTooltip() {
        if (activeTooltipOverlay) {
            activeTooltipOverlay.setMap(null);
            activeTooltipOverlay = null;
        }
    }

    function openTooltip(map, marker, item) {
        closeActiveTooltip();
        const style = managerStyle(item.manager);
        const pct = Number(item.percent) || 0;
        const bar = Math.max(0, Math.min(100, pct));
        const box = document.createElement('div');
        box.className = 'map-tip';
        box.innerHTML =
            `<button type="button" class="map-tip-close" aria-label="닫기">×</button>` +
            `<div class="tt-name">${escapeHtml(item.name)}</div>` +
            `<div class="tt-row"><span>담당자</span><b>${escapeHtml(item.manager || '-')}</b></div>` +
            `<div class="tt-row"><span>공번</span><b>${escapeHtml(item.no || '-')}</b></div>` +
            `<div class="tt-row"><span>공정률</span><span class="tt-pct">${pct}%</span></div>` +
            `<div class="tt-bar"><div style="width:${bar}%;background:${style.color}"></div></div>`;
        const overlay = new kakao.maps.CustomOverlay({
            content: box,
            position: marker.getPosition(),
            yAnchor: 1.42,
            zIndex: 1000,
            clickable: true,
        });
        box.querySelector('.map-tip-close').addEventListener('click', (e) => {
            e.stopPropagation();
            closeActiveTooltip();
        });
        overlay.setMap(map);
        activeTooltipOverlay = overlay;
        // 가장자리 핀의 툴팁이 지도 밖으로 잘리지 않도록, 클릭한 핀을 중앙으로 이동
        if (typeof map.panTo === 'function') {
            map.panTo(marker.getPosition());
        }
    }

    function loadKakaoSdk() {
        return new Promise((resolve, reject) => {
            if (window.kakao && window.kakao.maps) { resolve(); return; }
            const existing = document.getElementById('kakao-maps-sdk');
            if (existing) {
                existing.addEventListener('load', () => resolve());
                existing.addEventListener('error', () => reject(new Error('sdk load error')));
                return;
            }
            const script = document.createElement('script');
            script.id = 'kakao-maps-sdk';
            script.async = true;
            script.src = `//dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(kakaoMapJsKey)}&autoload=false&libraries=services,clusterer`;
            script.addEventListener('load', () => resolve());
            script.addEventListener('error', () => reject(new Error('sdk load error')));
            document.head.appendChild(script);
        });
    }

    async function renderProgressMap() {
        const mapEl = document.getElementById('progressMap');
        if (!mapEl) return;

        const center = new kakao.maps.LatLng(ANYANG_CENTER.lat, ANYANG_CENTER.lng);
        mapInstance = new kakao.maps.Map(mapEl, { center, level: 7 });
        mapInstance.setMaxLevel(11);
        kakao.maps.event.addListener(mapInstance, 'click', closeActiveTooltip);

        MONTHLY_PROGRESS_DATA = await loadProgressSites();

        const geocoder = new kakao.maps.services.Geocoder();
        const places = new kakao.maps.services.Places();
        const cache = loadGeoCache();
        let cacheDirty = false;

        const markers = [];
        const bounds = new kakao.maps.LatLngBounds();
        const imageCache = {};

        for (const item of MONTHLY_PROGRESS_DATA) {
            let coord = null;
            if (item.lat != null && item.lng != null) {
                // 관리 페이지에서 지정한 위치 — 지오코딩 없이 그대로 사용(울산 튐 방지)
                coord = { lat: Number(item.lat), lng: Number(item.lng) };
            } else {
                const cacheKey = (item.name || '') + '|' + (item.addr || '');
                coord = cache[cacheKey];
                if (coord === undefined) {
                    coord = await geocodeQueries(geocoder, places, buildQueriesForItem(item), center);
                    cache[cacheKey] = coord; // 실패(null)도 캐시해 재시도 폭주 방지
                    cacheDirty = true;
                }
            }
            if (!coord) continue;

            const style = managerStyle(item.manager);
            if (!imageCache[style.color]) {
                imageCache[style.color] = new kakao.maps.MarkerImage(
                    pinImageSrc(style),
                    new kakao.maps.Size(40, 48),
                    { offset: new kakao.maps.Point(20, 47) }
                );
            }
            const position = new kakao.maps.LatLng(coord.lat, coord.lng);
            const marker = new kakao.maps.Marker({ position, image: imageCache[style.color], title: item.name });
            kakao.maps.event.addListener(marker, 'click', () => openTooltip(mapInstance, marker, item));
            markers.push(marker);
            bounds.extend(position);
        }

        if (cacheDirty) saveGeoCache(cache);

        const clusterer = new kakao.maps.MarkerClusterer({
            map: mapInstance,
            averageCenter: true,
            minLevel: 6,
            gridSize: 60,
            disableClickZoom: false,
            styles: [{
                width: '46px', height: '46px',
                background: 'rgba(33, 86, 156, 0.88)',
                borderRadius: '23px',
                color: '#fff', textAlign: 'center', lineHeight: '46px',
                fontWeight: '800', fontSize: '15px',
                border: '3px solid rgba(255,255,255,0.92)',
            }],
        });
        clusterer.addMarkers(markers);

        const badge = document.getElementById('mapCountBadge');
        if (badge) badge.textContent = `표시 ${markers.length}건 · 자동`;

        if (markers.length > 0) {
            mapInstance.setBounds(bounds);
            setMapPlaceholder('', false);
        } else {
            setMapPlaceholder('표시할 공사 위치를 찾지 못했습니다.', true);
        }
    }

    async function fetchPublicConfig() {
        try {
            const res = await fetch('/api/public-config');
            if (!res.ok) return;
            const cfg = await res.json();
            kakaoMapJsKey = cfg.kakaoMapJsKey || '';
        } catch (_e) {
            // noop — 키 없으면 아래에서 안내 플레이스홀더 표시
        }
    }

    async function initMapHome() {
        await fetchPublicConfig();
        if (!kakaoMapJsKey) {
            setMapPlaceholder('카카오맵 JavaScript 키가 설정되지 않았습니다. 서버 .env의 KAKAO_MAP_JS_KEY를 설정하면 지도가 표시됩니다.', true);
            return;
        }
        setMapPlaceholder('지도를 불러오는 중...', true);
        try {
            await loadKakaoSdk();
        } catch (_e) {
            setMapPlaceholder('카카오맵 SDK 로드 실패 — JS 키/도메인 등록을 확인해 주세요.', true);
            return;
        }
        kakao.maps.load(() => {
            renderProgressMap().catch(() => {
                setMapPlaceholder('지도 렌더링 중 오류가 발생했습니다.', true);
            });
        });
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

    // ═══════════════════════════ 외출/행선표 ═══════════════════════════

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
        await loadWorkerStatusHome();
    }

    async function handleWorkerLocationClickHome(userName, currentLocation) {
        const decodedName = decodeURIComponent(userName || '');
        const decodedLocation = decodeURIComponent(currentLocation || '');
        const next = prompt('행선(목적지)을 입력하세요.', decodedLocation || '');
        if (next === null) return;
        const ok = await saveWorkerStatusPatch(decodedName, { location: next.trim() });
        if (!ok) return;
        await loadWorkerStatusHome();
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
        await loadWorkerStatusHome();
    }

    async function clearWorkerReturnTimeHome() {
        const target = workerReturnTimeTargetUser;
        if (!target) return;
        const ok = await saveWorkerStatusPatch(target, { until_time: '' });
        if (!ok) return;
        if (workerReturnTimeModal) workerReturnTimeModal.hide();
        await loadWorkerStatusHome();
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
        renderTotalProgressChartHome();
        loadTotalProgressHome();
        loadMaterialsHome();
        renderWeatherPlaceholder();
        initMapHome();
        await Promise.all([loadWorkerStatusHome(), loadFrequentSitesHome(), loadWeatherHome()]);
        setInterval(() => {
            updateNowLabel();
            loadTotalProgressHome();
            loadMaterialsHome();
            loadWorkerStatusHome();
            loadFrequentSitesHome();
            loadWeatherHome();
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
