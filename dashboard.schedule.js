(function () {
    const DAY_COLLAPSE_LIMIT = 4;
    const quickAddSelectedPersonNames = new Set();

    const ERP_SCHEMA = [
        { label: '상용직',   dayKey: 'regular_day',   nightKey: 'regular_night' },
        { label: '일용직',   dayKey: 'daily_day',      nightKey: 'daily_night' },
        { label: '모범신호수', dayKey: 'signalman_day', nightKey: 'signalman_night' },
        { label: '6W',       dayKey: 'w6_day',         nightKey: 'w6_night' },
        { label: '3W',       dayKey: 'w3_day',         nightKey: 'w3_night' },
        { label: '덤프15T',  dayKey: 'dump15t_day',    nightKey: 'dump15t_night' },
        { label: '크레인',   dayKey: 'crane_day',      nightKey: 'crane_night' },
        { label: '물청소차', dayKey: 'watertruck_day', nightKey: 'watertruck_night' },
        { label: 'MCM',      dayKey: 'mcm_day',        nightKey: 'mcm_night' },
        { label: '접속',     dayKey: 'connection_day', nightKey: 'connection_night' },
        { label: '외주1',    singleKey: 'outsource_1' },
        { label: '외주2',    singleKey: 'outsource_2' },
    ];

    // ── 수주대장 자동완성 ────────────────────────────────────────────────────
    let _constructionListCache = null;
    let _acDropdown = null;
    let _acCurrentTaskInput = null;
    let _acCurrentCodeInput = null;
    let _acActiveIdx = -1;

    async function fetchConstructionList() {
        if (_constructionListCache !== null) return _constructionListCache;
        try {
            const res = await fetch('/api/schedules/construction-list');
            if (!res.ok) { _constructionListCache = []; return []; }
            const data = await res.json();
            _constructionListCache = data.data || [];
        } catch { _constructionListCache = []; }
        return _constructionListCache;
    }

    function filterConstructionList(query) {
        if (!query || query.length < 1 || !_constructionListCache) return [];
        const q = query.toLowerCase();
        return _constructionListCache
            .filter(i => i.code.toLowerCase().includes(q) || i.name.toLowerCase().includes(q))
            .slice(0, 15);
    }

    function getOrCreateAcDropdown() {
        if (!_acDropdown) {
            _acDropdown = document.createElement('div');
            _acDropdown.className = 'construction-ac-dropdown';
            _acDropdown.style.display = 'none';
            document.body.appendChild(_acDropdown);
        }
        return _acDropdown;
    }

    function positionAcDropdown(inputEl) {
        const rect = inputEl.getBoundingClientRect();
        const dd = getOrCreateAcDropdown();
        dd.style.top = (rect.bottom + window.scrollY + 2) + 'px';
        dd.style.left = (rect.left + window.scrollX) + 'px';
        dd.style.width = Math.max(rect.width, 300) + 'px';
    }

    function hideAcDropdown() {
        if (_acDropdown) _acDropdown.style.display = 'none';
        _acActiveIdx = -1;
    }

    function selectAcItem(item) {
        if (_acCurrentTaskInput) _acCurrentTaskInput.value = item.name;
        if (_acCurrentCodeInput) _acCurrentCodeInput.value = item.code;
        hideAcDropdown();
    }

    function renderAcDropdown(results, inputEl) {
        const dd = getOrCreateAcDropdown();
        if (!results.length) { dd.style.display = 'none'; return; }
        positionAcDropdown(inputEl);
        _acActiveIdx = -1;
        dd.innerHTML = results.map((item, i) =>
            `<div class="construction-ac-item" data-idx="${i}">` +
            `<span class="ac-code">${escapeHtml(item.code)}</span>` +
            `<span class="ac-name">${escapeHtml(item.name)}</span>` +
            (item.work_type ? `<span class="ac-badge">${escapeHtml(item.work_type)}</span>` : '') +
            `</div>`
        ).join('');
        dd.querySelectorAll('.construction-ac-item').forEach((el, i) => {
            el.addEventListener('mousedown', e => { e.preventDefault(); selectAcItem(results[i]); });
        });
        dd.style.display = 'block';
    }

    function handleAcKeydown(e, results) {
        const items = _acDropdown ? _acDropdown.querySelectorAll('.construction-ac-item') : [];
        if (!items.length) return;
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            _acActiveIdx = Math.min(_acActiveIdx + 1, items.length - 1);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            _acActiveIdx = Math.max(_acActiveIdx - 1, 0);
        } else if (e.key === 'Enter' && _acActiveIdx >= 0) {
            e.preventDefault();
            selectAcItem(results[_acActiveIdx]);
            return;
        } else if (e.key === 'Escape') {
            hideAcDropdown(); return;
        } else { return; }
        items.forEach((el, i) => el.classList.toggle('ac-active', i === _acActiveIdx));
    }

    function attachConstructionAutocomplete(taskInputId, codeInputId) {
        const taskInput = document.getElementById(taskInputId);
        const codeInput = document.getElementById(codeInputId);
        if (!taskInput || !codeInput) return;
        getOrCreateAcDropdown();

        async function onInput(e) {
            _acCurrentTaskInput = taskInput;
            _acCurrentCodeInput = codeInput;
            await fetchConstructionList();
            const results = filterConstructionList(e.target.value);
            renderAcDropdown(results, e.target);
        }

        [taskInput, codeInput].forEach(input => {
            input.addEventListener('input', onInput);
            input.addEventListener('focus', async (e) => {
                _acCurrentTaskInput = taskInput;
                _acCurrentCodeInput = codeInput;
                if (e.target.value.length >= 1) {
                    await fetchConstructionList();
                    renderAcDropdown(filterConstructionList(e.target.value), e.target);
                }
            });
            input.addEventListener('blur', () => setTimeout(hideAcDropdown, 180));
            input.addEventListener('keydown', e => {
                handleAcKeydown(e, filterConstructionList(input.value));
            });
        });
    }
    // ────────────────────────────────────────────────────────────────────────

    function erpDataSummaryLine(erpData) {
        if (!erpData) return '';
        const data = typeof erpData === 'string'
            ? (() => { try { return JSON.parse(erpData); } catch { return {}; } })()
            : erpData;
        const parts = [];
        ERP_SCHEMA.forEach(row => {
            if (row.dayKey) {
                const day = Number(data[row.dayKey] || 0);
                const night = Number(data[row.nightKey] || 0);
                if (day > 0 && night > 0) parts.push(`${row.label} ${day}주/${night}야`);
                else if (day > 0) parts.push(`${row.label} ${day}`);
                else if (night > 0) parts.push(`${row.label} ${night}야`);
            } else if (row.singleKey) {
                const val = Number(data[row.singleKey] || 0);
                if (val > 0) parts.push(`${row.label} ${val}`);
            }
        });
        return parts.join(' · ');
    }

    function readErpData(prefix) {
        const d = {};
        ERP_SCHEMA.forEach(row => {
            if (row.dayKey)    d[row.dayKey]    = Number(document.getElementById(`${prefix}_${row.dayKey}`)?.value   || 0);
            if (row.nightKey)  d[row.nightKey]  = Number(document.getElementById(`${prefix}_${row.nightKey}`)?.value || 0);
            if (row.singleKey) d[row.singleKey] = Number(document.getElementById(`${prefix}_${row.singleKey}`)?.value || 0);
        });
        return d;
    }

    function writeErpData(prefix, erpData) {
        const data = typeof erpData === 'string' ? (() => { try { return JSON.parse(erpData); } catch { return {}; } })() : (erpData || {});
        ERP_SCHEMA.forEach(row => {
            if (row.dayKey)    { const el = document.getElementById(`${prefix}_${row.dayKey}`);    if (el) el.value = data[row.dayKey]    ?? 0; }
            if (row.nightKey)  { const el = document.getElementById(`${prefix}_${row.nightKey}`);  if (el) el.value = data[row.nightKey]  ?? 0; }
            if (row.singleKey) { const el = document.getElementById(`${prefix}_${row.singleKey}`); if (el) el.value = data[row.singleKey] ?? 0; }
        });
    }

    function resetErpData(prefix) {
        ERP_SCHEMA.forEach(row => {
            if (row.dayKey)    { const el = document.getElementById(`${prefix}_${row.dayKey}`);    if (el) el.value = 0; }
            if (row.nightKey)  { const el = document.getElementById(`${prefix}_${row.nightKey}`);  if (el) el.value = 0; }
            if (row.singleKey) { const el = document.getElementById(`${prefix}_${row.singleKey}`); if (el) el.value = 0; }
        });
    }

    function getScheduleState() {
        if (!window.__dashboardScheduleState) {
            window.__dashboardScheduleState = {
                expandedDayDateKeys: null,
            };
        }
        if (!window.__dashboardScheduleState.expandedDayDateKeys) {
            window.__dashboardScheduleState.expandedDayDateKeys = new Set();
        }
        return window.__dashboardScheduleState;
    }

    function collectExpandedDayFoldKeys() {
        const board = document.getElementById('scheduleBoard');
        if (!board) return;
        const st = getScheduleState();
        st.expandedDayDateKeys.clear();
        board.querySelectorAll('.day-fold-toggle-btn[data-expanded="1"]').forEach((btn) => {
            const enc = btn.getAttribute('data-date-key');
            if (enc) st.expandedDayDateKeys.add(decodeURIComponent(enc));
        });
    }

    function restoreExpandedDayFoldKeys() {
        const board = document.getElementById('scheduleBoard');
        if (!board) return;
        const st = getScheduleState();
        if (!st.expandedDayDateKeys || st.expandedDayDateKeys.size === 0) return;
        st.expandedDayDateKeys.forEach((rawDateKey) => {
            const enc = encodeURIComponent(rawDateKey);
            const wrap = board.querySelector(`.calendar-day-items[data-date-key="${enc}"]`);
            const btn = board.querySelector(`.day-fold-toggle-btn[data-date-key="${enc}"]`);
            if (!wrap || !btn) return;
            wrap.classList.remove('collapsed');
            btn.setAttribute('data-expanded', '1');
            btn.textContent = dayFoldToggleLabel(0, true);
        });
    }

    function dayFoldToggleLabel(hiddenCount, expanded) {
        if (expanded) return '간단히';
        const count = Math.max(Number(hiddenCount) || 0, 0);
        return `+${count} 더보기`;
    }

    /** DB에 [공사1팀] 접두가 남아 있어도 제목만 보이게(레거시 호환) */
    function displayScheduleTaskTitle(taskRaw) {
        const s = String(taskRaw || '').trim();
        return s.replace(/^\[(?:공사[123]팀|기타)\]\s*/, '');
    }

    function isPhotoPlanPendingReview(item) {
        return String(item.source_kind || '').trim() === 'photo_plan' && !Number(item.photo_plan_acknowledged || 0);
    }

    async function acknowledgePhotoPlanImport(scheduleId) {
        const id = Number(scheduleId);
        if (!id) return;
        try {
            const res = await fetch('/api/schedules/acknowledge-photo-plan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ schedule_id: id }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                showSaveToast(data.detail || '처리에 실패했습니다.', 'error');
                return;
            }
            showSaveToast(data.message || '검토 완료로 표시했습니다.', 'success');
            await loadSchedules();
        } catch (_e) {
            showSaveToast('요청 중 오류가 발생했습니다.', 'error');
        }
    }

    function getScheduleFilters() {
        const todayOnly = document.getElementById('todayOnlyCheck').checked;
        const selectedDate = document.getElementById('scheduleTargetDate').value;
        const keyword = document.getElementById('scheduleSearchKeyword').value.trim().toLowerCase();
        return { todayOnly, selectedDate, keyword };
    }

    function updateBoardViewModeLabel(todayOnly, selectedDate) {
        const el = document.getElementById('boardViewModeLabel');
        if (!el) return;
        if (todayOnly) {
            el.textContent = '조회 모드: 오늘만';
            return;
        }
        if (selectedDate) {
            el.textContent = `조회 모드: 특정일(${selectedDate})`;
            return;
        }
        const d = new Date(`${currentBoardMonth}T00:00:00`);
        if (Number.isNaN(d.getTime())) {
            el.textContent = '조회 모드: 월 전체';
            return;
        }
        el.textContent = `조회 모드: ${d.getFullYear()}년 ${String(d.getMonth() + 1).padStart(2, '0')}월 전체`;
    }

    let _loadSchedulesInflight = false;
    let _loadSchedulesPending = false;
    async function loadSchedules() {
        // race condition 가드: 동시에 호출되면 직렬화 — 이미 진행 중이면 1회만 큐잉.
        if (_loadSchedulesInflight) {
            _loadSchedulesPending = true;
            return;
        }
        _loadSchedulesInflight = true;
        const board = document.getElementById('scheduleBoard');
        const { todayOnly, selectedDate, keyword } = getScheduleFilters();
        const todayStr = formatLocalDateYYYYMMDD();
        const monthlyRange = getMonthRange(currentBoardMonth || getMonthStart(todayStr));
        const queryDate = todayOnly ? todayStr : (selectedDate || '');
        const prevActiveScheduleId = getActiveScheduleCardId();
        updateBoardViewModeLabel(todayOnly, selectedDate);

        try {
            let url = '/api/schedules/today';
            if (queryDate) {
                url = `/api/schedules/today?date=${encodeURIComponent(queryDate)}`;
            } else {
                url = `/api/schedules/today?range_start=${encodeURIComponent(monthlyRange.start)}&range_end=${encodeURIComponent(monthlyRange.end)}`;
            }
            const response = await fetch(url);
            const data = await response.json();
            const rows = Array.isArray(data.data) ? data.data : [];
            let filteredRows = keyword
                ? rows.filter((item) => {
                    const merged = `${item.task || ''} ${item.person || ''} ${item.details || ''} ${item.work_code || ''}`.toLowerCase();
                    return merged.includes(keyword);
                })
                : rows;
            filteredRows = filteredRows.filter(scheduleMatchesAppliedPersonFilter);
            scheduleMap.clear();
            filteredRows.forEach((item) => scheduleMap.set(String(item.id), item));

            const groupedData = filteredRows.reduce((acc, item) => {
                const dateKey = item.date || '날짜 미상';
                if (!acc[dateKey]) acc[dateKey] = [];
                acc[dateKey].push(item);
                return acc;
            }, {});
            Object.keys(groupedData).forEach((dateKey) => {
                groupedData[dateKey].sort((a, b) => {
                    const ap = categoryPriority(a.category);
                    const bp = categoryPriority(b.category);
                    if (ap !== bp) return ap - bp;
                    if (ap === 1) {
                        const as = constructionShiftPriority(a);
                        const bs = constructionShiftPriority(b);
                        if (as !== bs) return as - bs;
                    }
                    return String(a.task || '').localeCompare(String(b.task || ''), 'ko');
                });
            });

            let sortedDates = [];
            if (todayOnly) {
                sortedDates = [todayStr];
            } else if (selectedDate) {
                sortedDates = [selectedDate];
            } else {
                sortedDates = monthlyRange.dates;
            }

            collectExpandedDayFoldKeys();

            const boardHTML = isMobileViewport()
                ? renderMobileCalendar(sortedDates, groupedData, todayStr)
                : renderDesktopCalendar(sortedDates, groupedData, todayStr);

            board.innerHTML = boardHTML;
            restoreActiveScheduleCard(prevActiveScheduleId);
            restoreExpandedDayFoldKeys();
            updateLastSyncTime();
            const sideTasks = [];
            if (document.getElementById('workerStatusList')) sideTasks.push(loadWorkerStatus());
            if (sideTasks.length) await Promise.all(sideTasks);

        } catch (error) {
            console.error('데이터 갱신 실패:', error);
            document.getElementById('lastUpdated').innerText = '동기화 지연 중...';
        } finally {
            _loadSchedulesInflight = false;
            if (_loadSchedulesPending) {
                _loadSchedulesPending = false;
                window.setTimeout(loadSchedules, 0);
            }
        }
    }

    function normalizeShiftType(raw) {
        const val = String(raw || '').trim();
        if (val === '주간') return '주간';
        if (val === '야간' || val === '심야') return '야간';
        return '';
    }

    function normalizeCategoryForSave(rawCategory) {
        const ui = displayCategoryLabel(rawCategory || '').trim();
        if (ui === '공사') return '공사 일정';
        if (ui === '일정') return '일정';
        return '일정';
    }

    function applyDefaultShiftType(rawCategory, rawShiftType) {
        const normalized = normalizeShiftType(rawShiftType || '');
        const ui = displayCategoryLabel(rawCategory || '').trim();
        if (ui === '공사') return normalized || '주간';
        return normalized;
    }

    function shiftBadgeClass(shiftType) {
        const s = normalizeShiftType(shiftType);
        if (s === '주간') return 'shift-day';
        if (s === '야간') return 'shift-night';
        return '';
    }

    function constructionShiftCardClass(item) {
        const cat = displayCategoryLabel(item?.category || '').trim();
        if (cat !== '공사') return '';
        return applyDefaultShiftType(item?.category || '', item?.shift_type || '') === '야간' ? 'construction-shift-night' : 'construction-shift-day';
    }

    function fullPersonLabel(personRaw) {
        const raw = String(personRaw || '').trim();
        if (!raw) return '';
        const names = raw.split(/[,\n]/).map((s) => s.trim()).filter(Boolean);
        return names.join(', ');
    }

    function isMobileViewport() {
        return window.matchMedia('(max-width: 768px)').matches;
    }

    function categoryPriority(category) {
        const c = displayCategoryLabel(category || '').trim();
        if (!c || c === '공사') return 1;
        if (c === '일정') return 4;
        return 9;
    }

    function constructionShiftPriority(item) {
        const category = displayCategoryLabel(item?.category || '').trim();
        if (category !== '공사') return 0;
        const shiftType = applyDefaultShiftType(item?.category || '', item?.shift_type || '');
        if (shiftType === '주간') return 1;
        if (shiftType === '야간') return 2;
        return 3;
    }

    function compactCategoryClass(category) {
        const c = displayCategoryLabel(category || '').trim();
        if (!c || c === '공사') return 'cat-construction';
        if (c === '일정') return 'cat-schedule';
        return 'cat-schedule';
    }

    function detailLineCount(text) {
        const lines = String(text || '')
            .replace(/\r\n/g, '\n')
            .split('\n')
            .map((s) => s.trim())
            .filter(Boolean);
        return lines.length;
    }

    function detailInlineHtml(text) {
        return String(text || '')
            .split('\n')
            .map((line) => escapeHtml(line))
            .join('<br>');
    }

    function dayAddButtonHtml(dateKey) {
        const encodedDate = encodeURIComponent(dateKey);
        const ariaLabel = `${dateKey} 일정 추가`;
        return `<button type="button" class="day-add-btn" data-date-key="${encodedDate}" aria-label="${escapeHtml(ariaLabel)}" title="일정 추가">+</button>`;
    }

    function personTokens(personRaw) {
        return String(personRaw || '').split(/[,\n]/).map((s) => s.trim()).filter(Boolean);
    }

    function syncQuickAddPersonInput() {
        const personInput = document.getElementById('quickAddPerson');
        if (!personInput) return;
        personInput.value = Array.from(quickAddSelectedPersonNames).join(', ');
    }

    function hydrateQuickAddSelectedNamesFromInput() {
        const personInput = document.getElementById('quickAddPerson');
        quickAddSelectedPersonNames.clear();
        personTokens(personInput?.value || '').forEach((name) => quickAddSelectedPersonNames.add(name));
    }

    function toggleQuickAddStaffName(name) {
        const trimmed = String(name || '').trim();
        if (!trimmed) return;
        if (quickAddSelectedPersonNames.has(trimmed)) quickAddSelectedPersonNames.delete(trimmed);
        else quickAddSelectedPersonNames.add(trimmed);
        syncQuickAddPersonInput();
        paintQuickAddStaffButtons();
    }

    function paintQuickAddStaffButtons() {
        const box = document.getElementById('quickAddFieldStaffList');
        if (!box) return;
        box.querySelectorAll('.quick-add-staff-btn').forEach((btn) => {
            const name = decodeURIComponent(btn.getAttribute('data-name') || '');
            btn.classList.toggle('active', quickAddSelectedPersonNames.has(name));
        });
    }

    async function loadQuickAddFieldStaffOptions() {
        const box = document.getElementById('quickAddFieldStaffList');
        if (!box) return;
        box.innerHTML = '<span class="small text-muted">불러오는 중...</span>';
        try {
            const res = await fetch('/api/schedules/field-staff');
            const data = await res.json();
            if (!res.ok) {
                box.innerHTML = `<span class="small text-danger">${escapeHtml(data.detail || '인원 목록을 불러오지 못했습니다.')}</span>`;
                return;
            }
            const rows = data.data || [];
            const validNames = rows
                .map((r) => String(r.name || '').trim())
                .filter(Boolean);
            if (!validNames.length) {
                box.innerHTML = '<span class="small text-muted">등록된 인원이 없습니다.</span>';
                return;
            }
            box.innerHTML = validNames.map((name) =>
                `<button type="button" class="quick-add-staff-btn" data-name="${encodeURIComponent(name)}">${escapeHtml(name)}</button>`
            ).join('');
            box.querySelectorAll('.quick-add-staff-btn').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const name = decodeURIComponent(btn.getAttribute('data-name') || '');
                    toggleQuickAddStaffName(name);
                });
            });
            paintQuickAddStaffButtons();
        } catch (_e) {
            box.innerHTML = '<span class="small text-danger">인원 목록을 불러오지 못했습니다.</span>';
        }
    }

    function bindQuickAddSectionEvents() {
        const peopleSection = document.getElementById('quickAddPeopleSection');
        if (!peopleSection || peopleSection.dataset.bound === '1') return;
        peopleSection.dataset.bound = '1';
        peopleSection.addEventListener('toggle', () => {
            if (!peopleSection.open) return;
            loadQuickAddFieldStaffOptions();
        });
    }

    function renderCompactScheduleItem(item) {
        const catClass = compactCategoryClass(item.category);
        const detailLine = String(item.details || '').trim();
        const detailLines = detailLineCount(detailLine);
        const shiftType = applyDefaultShiftType(item.category || '', item.shift_type || '');
        const shiftClass = shiftBadgeClass(shiftType);
        const workCode = String(item.work_code || '').trim();
        const taskLabel = `${escapeHtml(displayScheduleTaskTitle(item.task) || '공사명 미기재')}`;
        const badgeParts = [];
        if (shiftType) badgeParts.push(`<span class="schedule-shift-badge ${shiftClass}">${shiftType}</span>`);
        if (workCode) {
            badgeParts.push(`<span class="schedule-workcode-badge">${escapeHtml(workCode)}</span>`);
        }
        if (isPhotoPlanPendingReview(item)) {
            badgeParts.push('<span class="schedule-source-badge">자동추출</span>');
        }
        const badgesHtml = badgeParts.length
            ? `<span class="schedule-meta-badges">${badgeParts.join('')}</span>`
            : '';
        const shiftCardClass = constructionShiftCardClass(item);
        const photoPlanClass = isPhotoPlanPendingReview(item) ? ' schedule-item-photo-plan' : '';
        const erpSummary = erpDataSummaryLine(item.erp_data);
        const detailModalBtn = detailLine && detailLines >= 3
            ? `<button type="button" class="btn btn-sm btn-outline-dark mt-1" onclick="event.stopPropagation(); openScheduleDetailModal('${item.id}')">상세 정보</button>`
            : '';
        return `
                <div class="schedule-compact-item ${catClass} ${shiftCardClass}${photoPlanClass}" data-id="${item.id}">
                    <div class="schedule-compact-task"><span class="schedule-task-head"><span class="schedule-category-dot ${catClass}"></span>${taskLabel}</span>${badgesHtml}</div>
                    ${erpSummary ? `<div class="schedule-compact-person" style="color:#2d5fa0;font-size:0.78rem;">📋 ${escapeHtml(erpSummary)}</div>` : ''}
                    ${scheduleViewOptions.showDetails && detailLine ? `<div class="schedule-compact-detail-preview">📝 ${escapeHtml(detailLine)}</div>` : ''}
                    <div class="schedule-action-panel">
                        ${detailLine && detailLines <= 2 ? `<div class="detail-text">📝 ${detailInlineHtml(detailLine)}</div>` : ''}
                        ${detailModalBtn}
                        <div>
                            <button type="button" class="btn btn-sm btn-outline-secondary mt-1" id="drive-upload-label-${item.id}" onclick="event.stopPropagation(); document.getElementById('drive-file-${item.id}').click()">📂 드라이브에 사진 업로드</button>
                            <input type="file" id="drive-file-${item.id}" accept="image/*,application/pdf,video/*" multiple style="position:fixed;top:-9999px;left:-9999px;width:1px;height:1px;opacity:0" onchange="event.stopPropagation(); handleDriveUpload(event, '${item.id}')">
                        </div>
                        <div class="schedule-actions mt-2 d-flex gap-2 justify-content-end flex-wrap">
                            ${isPhotoPlanPendingReview(item) ? `<button type="button" class="btn btn-sm btn-outline-success" onclick="event.stopPropagation(); acknowledgePhotoPlanImport(${item.id})">추출 검토 완료</button>` : ''}
                            <button class="btn btn-sm btn-outline-primary" onclick="event.stopPropagation(); openEditRequestById('${item.id}')">수정</button>
                            <button class="btn btn-sm btn-outline-danger" onclick="event.stopPropagation(); requestDeleteById('${item.id}')">삭제</button>
                        </div>
                    </div>
                </div>
            `;
    }

    function renderDayItemsSection(dateKey, dayItems) {
        const itemCount = dayItems.length;
        if (itemCount === 0) {
            return '<div class="calendar-empty-line"></div>';
        }
        const encodedDate = encodeURIComponent(dateKey);
        const needFold = itemCount > DAY_COLLAPSE_LIMIT;
        const listClass = needFold ? 'calendar-day-items collapsed' : 'calendar-day-items';
        const listHtml = dayItems.map((item) => renderCompactScheduleItem(item)).join('');
        const toggleHtml = needFold
            ? `<button type="button" class="day-fold-toggle-btn" data-date-key="${encodedDate}" data-expanded="0">${dayFoldToggleLabel(itemCount - DAY_COLLAPSE_LIMIT, false)}</button>`
            : '';
        return `<div class="${listClass}" data-date-key="${encodedDate}">${listHtml}</div>${toggleHtml}`;
    }

    function renderMobileCalendar(sortedDates, groupedData, todayStr) {
        const todayCount = (groupedData[todayStr] || []).length;
        let html = `<div class="mobile-today-pin">오늘 일정: ${todayCount}건</div>`;
        sortedDates.forEach((date) => {
            const dayName = getDayName(date);
            const dayItems = groupedData[date] || [];
            const todayClass = date === todayStr ? 'today' : '';
            html += `<div class="mobile-day-block"><div class="mobile-day-title ${todayClass}"><span class="calendar-date-main"><span>📅 ${escapeHtml(date)} ${dayName}${date === todayStr ? ' [오늘]' : ''}</span>${dayAddButtonHtml(date)}</span><span class="day-count-badge">${dayItems.length}건</span></div>`;
            html += renderDayItemsSection(date, dayItems);
            html += '</div>';
        });
        return html;
    }

    function renderDesktopCalendar(sortedDates, groupedData, todayStr) {
        const weekDays = ['일', '월', '화', '수', '목', '금', '토'];
        let html = '<div class="calendar-week-header">';
        weekDays.forEach((d, idx) => {
            const cls = idx === 0 ? 'sun' : (idx === 6 ? 'sat' : '');
            html += `<div class="calendar-weekday ${cls}">${d}</div>`;
        });
        html += '</div>';

        const firstDate = sortedDates[0];
        const lastDate = sortedDates[sortedDates.length - 1];
        const start = new Date(`${firstDate}T00:00:00`);
        const end = new Date(`${lastDate}T00:00:00`);
        start.setDate(start.getDate() - start.getDay());
        end.setDate(end.getDate() + (6 - end.getDay()));
        const visibleSet = new Set(sortedDates);

        html += '<div class="calendar-grid">';
        for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
            const dateKey = formatLocalDateYYYYMMDD(d);
            const dayIdx = d.getDay();
            const inRange = visibleSet.has(dateKey);
            const isToday = dateKey === todayStr;
            const dayItems = groupedData[dateKey] || [];
            const dayCls = dayIdx === 0 ? 'sun' : (dayIdx === 6 ? 'sat' : '');
            const classes = `calendar-cell ${dayCls} ${inRange ? '' : 'out-range'} ${isToday ? 'today' : ''}`.trim();

            html += `<div class="${classes}">`;
            const count = inRange ? dayItems.length : 0;
            const addBtn = inRange ? dayAddButtonHtml(dateKey) : '';
            html += `<div class="calendar-date-label"><span class="calendar-date-main"><span>${escapeHtml(dateKey)}${isToday ? ' [오늘]' : ''}</span>${addBtn}</span><span class="day-count-badge">${count}건</span></div>`;
            if (inRange) {
                html += renderDayItemsSection(dateKey, dayItems);
            }
            html += '</div>';
        }
        html += '</div>';
        return html;
    }

    function bindCompactItemActions() {
        const board = document.getElementById('scheduleBoard');
        board.addEventListener('click', (e) => {
            const dayAddBtn = e.target.closest('.day-add-btn');
            if (dayAddBtn) {
                e.preventDefault();
                e.stopPropagation();
                const encodedDate = dayAddBtn.getAttribute('data-date-key') || '';
                const dateKey = encodedDate ? decodeURIComponent(encodedDate) : '';
                if (!dateKey) return;
                openQuickAddForDate(dateKey);
                return;
            }
            const dayToggleBtn = e.target.closest('.day-fold-toggle-btn');
            if (dayToggleBtn) {
                e.preventDefault();
                e.stopPropagation();
                const encodedDate = dayToggleBtn.getAttribute('data-date-key') || '';
                if (!encodedDate) return;
                const dayItemsWrap = board.querySelector(`.calendar-day-items[data-date-key="${encodedDate}"]`);
                if (!dayItemsWrap) return;
                const isExpanded = dayItemsWrap.classList.toggle('collapsed') === false;
                dayToggleBtn.setAttribute('data-expanded', isExpanded ? '1' : '0');
                const hiddenCount = Math.max(dayItemsWrap.querySelectorAll('.schedule-compact-item').length - DAY_COLLAPSE_LIMIT, 0);
                dayToggleBtn.textContent = dayFoldToggleLabel(hiddenCount, isExpanded);
                if (!isExpanded) {
                    dayItemsWrap.scrollIntoView({ block: 'nearest' });
                }
                return;
            }
            const card = e.target.closest('.schedule-compact-item');
            if (!card) return;
            if (e.target.closest('button') || e.target.closest('input') || e.target.closest('textarea') || e.target.closest('label')) return;
            document.querySelectorAll('.schedule-compact-item.active').forEach((el) => {
                if (el !== card) el.classList.remove('active');
            });
            const wasActive = card.classList.contains('active');
            card.classList.toggle('active');
            if (!wasActive) {
                const scheduleId = card.getAttribute('data-id');
                if (scheduleId) loadAttachmentFeed(scheduleId);
            }
        });
        window.addEventListener('resize', () => {
            if (!isMobileViewport()) return;
            document.querySelectorAll('.schedule-compact-item.active').forEach((el) => el.classList.remove('active'));
        });
    }

    function getActiveScheduleCardId() {
        const activeCard = document.querySelector('.schedule-compact-item.active');
        if (!activeCard) return null;
        const rawId = activeCard.getAttribute('data-id');
        return rawId ? String(rawId) : null;
    }

    function restoreActiveScheduleCard(activeId) {
        if (!activeId) return;
        const target = document.querySelector(`.schedule-compact-item[data-id="${activeId}"]`);
        if (target) {
            target.classList.add('active');
            loadAttachmentFeed(activeId);
        }
    }

    function openEditRequestById(scheduleId) {
        const item = scheduleMap.get(String(scheduleId));
        if (!item) {
            showSaveToast('일정 정보를 찾을 수 없습니다. 새로고침 후 다시 시도하세요.', 'error');
            return;
        }
        document.getElementById('editScheduleId').value = String(item.id || '');
        document.getElementById('editDate').value = item.date || '';
        document.getElementById('editTask').value = item.task || '';
        document.getElementById('editPerson').value = item.person || '';
        document.getElementById('editDetails').value = item.details || '';
        document.getElementById('editCategory').value = normalizeCategoryForSave(item.category || '공사 일정');
        document.getElementById('editShiftType').value = applyDefaultShiftType(item.category || '공사 일정', item.shift_type || '');
        document.getElementById('editWorkCode').value = String(item.work_code || '').trim();
        writeErpData('editErp', item.erp_data || null);
        window.editRequestModal.show();
    }

    function openQuickAddForDate(dateKey) {
        const dateInput = document.getElementById('quickAddDate');
        const categoryInput = document.getElementById('quickAddCategory');
        const taskInput = document.getElementById('quickAddTask');
        const detailsInput = document.getElementById('quickAddDetails');
        const personInput = document.getElementById('quickAddPerson');
        const shiftInput = document.getElementById('quickAddShiftType');
        const workCodeInput = document.getElementById('quickAddWorkCode');
        const peopleSection = document.getElementById('quickAddPeopleSection');
        const otherSection = document.getElementById('quickAddOtherSection');
        const staffListBox = document.getElementById('quickAddFieldStaffList');
        if (!dateInput || !window.quickAddScheduleModal) return;
        quickAddSelectedPersonNames.clear();
        bindQuickAddSectionEvents();
        if (peopleSection) peopleSection.open = false;
        if (otherSection) otherSection.open = false;
        dateInput.value = String(dateKey || '').trim() || formatLocalDateYYYYMMDD();
        if (categoryInput) categoryInput.value = '공사 일정';
        if (taskInput) taskInput.value = '';
        if (detailsInput) detailsInput.value = '';
        if (personInput) {
            personInput.value = '';
            personInput.oninput = () => {
                hydrateQuickAddSelectedNamesFromInput();
                paintQuickAddStaffButtons();
            };
        }
        if (shiftInput) shiftInput.value = '';
        if (workCodeInput) workCodeInput.value = '';
        if (staffListBox) {
            staffListBox.innerHTML = '<span class="small text-muted">펼치면 인원 목록이 보입니다.</span>';
        }
        resetErpData('qaErp');
        window.quickAddScheduleModal.show();
        if (taskInput) taskInput.focus();
    }

    async function submitQuickAddSchedule() {
        const date = document.getElementById('quickAddDate')?.value.trim() || formatLocalDateYYYYMMDD();
        const category = normalizeCategoryForSave(document.getElementById('quickAddCategory')?.value.trim() || '공사 일정');
        const task = document.getElementById('quickAddTask')?.value.trim() || '';
        const details = document.getElementById('quickAddDetails')?.value.trim() || '';
        const personRaw = document.getElementById('quickAddPerson')?.value || '';
        const person = personTokens(personRaw).join(', ');
        const shiftType = applyDefaultShiftType(category, document.getElementById('quickAddShiftType')?.value.trim() || '');
        const workCode = document.getElementById('quickAddWorkCode')?.value.trim() || '';
        if (!task) {
            showSaveToast('작업/메모 제목을 입력하세요.', 'info');
            return;
        }
        const payload = {
            action_type: 'register',
            date,
            task,
            person,
            details,
            shift_type: shiftType,
            work_code: workCode,
            category,
            request_note: '',
            schedule_id: null,
            erp_data: readErpData('qaErp'),
        };
        const response = await fetch('/api/schedules/board/template-action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            showSaveToast(data.detail || '일정 등록에 실패했습니다.', 'error');
            return;
        }
        if (window.quickAddScheduleModal) window.quickAddScheduleModal.hide();
        showSaveToast(data.message || '일정을 등록했습니다.', 'success');
        await loadSchedules();
    }

    async function submitDirectEdit() {
        const scheduleId = Number(document.getElementById('editScheduleId').value);
        if (!scheduleId) {
            showSaveToast('수정 대상 일정 ID가 없습니다.', 'error');
            return;
        }

        const catVal = normalizeCategoryForSave(document.getElementById('editCategory').value.trim() || '공사 일정');
        const shiftVal = applyDefaultShiftType(catVal, document.getElementById('editShiftType').value.trim());
        const payload = {
            action: 'update',
            schedule_id: scheduleId,
            schedule_data: {
                date: document.getElementById('editDate').value.trim(),
                location: '',
                task: document.getElementById('editTask').value.trim(),
                person: document.getElementById('editPerson').value.trim(),
                details: document.getElementById('editDetails').value.trim(),
                category: catVal,
                shift_type: shiftVal,
                work_code: document.getElementById('editWorkCode').value.trim(),
                erp_data: readErpData('editErp'),
            }
        };

        if (!payload.schedule_data.task) {
            showSaveToast('공사명·작업 내용(task)은 필수입니다.', 'info');
            return;
        }
        const response = await fetch('/api/schedules/direct-update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                schedule_id: scheduleId,
                schedule_data: payload.schedule_data,
                reason: '현황판 인라인 수정'
            })
        });
        const result = await response.json();
        if (!response.ok) {
            showSaveToast(result.detail || result.message || '수정 실패', 'error');
            return;
        }
        window.editRequestModal.hide();
        showSaveToast(result.message || '수정되었습니다.', 'success');
        await loadSchedules();
    }

    async function requestDeleteById(scheduleId) {
        const item = scheduleMap.get(String(scheduleId));
        if (!item) {
            showSaveToast('일정 정보를 찾을 수 없습니다. 새로고침 후 다시 시도하세요.', 'error');
            return;
        }
        const confirmText = `해당 일정을 삭제하시겠습니까?\n[ID #${item.id}] ${item.task || ''}`;
        if (!confirm(confirmText)) return;

        const response = await fetch('/api/schedules/direct-delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                schedule_id: Number(item.id),
                reason: '현황판 인라인 삭제'
            })
        });
        const result = await response.json();
        if (!response.ok) {
            showSaveToast(result.detail || result.message || '삭제 실패', 'error');
            return;
        }
        showSaveToast(result.message || '삭제되었습니다.', 'success');
        await loadSchedules();
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

    async function saveWorkerStatusPatch(userName, patch) {
        const currentRowsRes = await fetch('/api/schedules/worker-status');
        const currentRowsJson = await currentRowsRes.json();
        const rows = currentRowsJson.data || [];
        const row = rows.find((r) => String(r.user_name) === String(userName)) || { user_name: userName, status: '사무실', location: '', until_time: '', note: '' };
        const payload = {
            user_name: userName,
            status: patch.status ?? row.status ?? '사무실',
            location: patch.location ?? row.location ?? '',
            until_time: patch.until_time ?? row.until_time ?? '',
            note: ''
        };
        const response = await fetch('/api/schedules/worker-status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) {
            showSaveToast(data.detail || '상태 저장 실패', 'error');
            return false;
        }
        return true;
    }

    async function handleWorkerStatusClick(userName, currentStatus) {
        const decodedName = decodeURIComponent(userName || '');
        const decodedStatus = decodeURIComponent(currentStatus || '사무실');
        const ok = await saveWorkerStatusPatch(decodedName, { status: nextStatus(decodedStatus) });
        if (ok) await loadWorkerStatus();
    }

    async function handleWorkerLocationClick(userName, currentLocation) {
        const decodedName = decodeURIComponent(userName || '');
        const decodedLocation = decodeURIComponent(currentLocation || '');
        const next = prompt('행선(목적지)을 입력하세요.', decodedLocation || '');
        if (next === null) return;
        const ok = await saveWorkerStatusPatch(decodedName, { location: next.trim() });
        if (ok) await loadWorkerStatus();
    }

    function autoFitWorkerLocationText() {
        const MAX_FONT_PX = 13;
        const MIN_NOWRAP_FONT_PX = 8;
        const WRAP_FONT_PX = 10;
        const STEP_PX = 0.5;
        const buttons = document.querySelectorAll('.worker-location-btn');
        buttons.forEach((btn) => {
            btn.classList.remove('allow-wrap');
            let size = MAX_FONT_PX;
            btn.style.fontSize = `${size}px`;
            btn.title = btn.textContent || '';
            while (size > MIN_NOWRAP_FONT_PX && btn.scrollWidth > btn.clientWidth) {
                size -= STEP_PX;
                btn.style.fontSize = `${size}px`;
            }
            if (btn.scrollWidth > btn.clientWidth) {
                btn.style.fontSize = `${WRAP_FONT_PX}px`;
                btn.classList.add('allow-wrap');
            }
        });
    }

    function openScheduleDetailModal(scheduleId) {
        const item = scheduleMap.get(String(scheduleId));
        const detail = item ? String(item.details || '').trim() : '';
        openDetailPreviewModal(encodeURIComponent(detail || '상세 정보가 없습니다.'));
    }

    function openDetailPreviewModal(encodedDetail) {
        const detail = decodeURIComponent(encodedDetail || '');
        document.getElementById('detailPreviewContent').textContent = detail || '상세 정보가 없습니다.';
        window.detailPreviewModal.show();
    }

    async function loadWorkerStatus() {
        const list = document.getElementById('workerStatusList');
        const railMode = rightColumnMode === 'rail';
        const workerExpanded = !railMode;
        const [statusRes, outingRes] = await Promise.all([
            fetch('/api/schedules/worker-status'),
            fetch('/api/schedules/outing-staff')
        ]);
        const data = await statusRes.json();
        const outingData = await outingRes.json();
        if (!statusRes.ok || !outingRes.ok) {
            list.innerHTML = '<li class="list-group-item text-danger">상태 조회 실패</li>';
            return;
        }
        const statusMap = new Map((data.data || []).map((r) => [String(r.user_name), r]));
        const outingStaff = outingData.data || [];
        if (outingStaff.length === 0) {
            list.innerHTML = '<li class="list-group-item text-muted">외출/행선표 인원 목록이 없습니다. 관리자 화면에서 인원을 등록하세요.</li>';
            return;
        }
        list.innerHTML = outingStaff.map((staff) => {
            const row = statusMap.get(String(staff.name)) || { user_name: staff.name, status: '사무실', location: '', until_time: '' };
            const safeName = escapeHtml(row.user_name);
            const safeStatus = escapeHtml(row.status || '사무실');
            const safeLoc = escapeHtml(row.location || '행선 입력');
            const metaInner = workerExpanded && row.status === '외출'
                ? `<button type="button" class="btn btn-link btn-sm p-0 text-decoration-none text-muted worker-location-btn" data-action="worker-location" data-name="${safeName}" data-location="${escapeHtml(row.location || '')}">${safeLoc}</button>`
                : '';
            return `
                <li class="list-group-item d-flex justify-content-between align-items-center py-2 gap-1">
                    <b class="worker-row-name text-truncate mb-0 min-w-0" style="max-width: 48%;">${safeName}</b>
                    <div class="d-flex align-items-center justify-content-end gap-1 flex-shrink-0 flex-grow-1" style="min-width: 0;">
                        <button type="button" class="btn btn-sm badge status-badge-sm ${statusBadgeClass(row.status)}" data-action="worker-status" data-name="${safeName}" data-status="${safeStatus}">${statusLabelText(row.status)}</button>
                        <span class="text-muted small worker-outing-meta text-end">${metaInner}</span>
                    </div>
                </li>
            `;
        }).join('');
        // 이벤트 위임: data-action="worker-status"/"worker-location" 클릭 처리.
        if (!list.dataset.workerDelegationBound) {
            list.dataset.workerDelegationBound = '1';
            list.addEventListener('click', (e) => {
                const target = e.target.closest('[data-action]');
                if (!target || !list.contains(target)) return;
                const action = target.getAttribute('data-action');
                const name = target.getAttribute('data-name') || '';
                if (action === 'worker-status') {
                    handleWorkerStatusClick(encodeURIComponent(name), encodeURIComponent(target.getAttribute('data-status') || '사무실'));
                } else if (action === 'worker-location') {
                    handleWorkerLocationClick(encodeURIComponent(name), encodeURIComponent(target.getAttribute('data-location') || ''));
                }
            });
        }
        autoFitWorkerLocationText();
    }

    window.getScheduleFilters = getScheduleFilters;
    window.updateBoardViewModeLabel = updateBoardViewModeLabel;
    window.loadSchedules = loadSchedules;
    window.acknowledgePhotoPlanImport = acknowledgePhotoPlanImport;
    window.normalizeShiftType = normalizeShiftType;
    window.applyDefaultShiftType = applyDefaultShiftType;
    window.normalizeCategoryForSave = normalizeCategoryForSave;
    window.shiftBadgeClass = shiftBadgeClass;
    window.constructionShiftCardClass = constructionShiftCardClass;
    window.fullPersonLabel = fullPersonLabel;
    window.isMobileViewport = isMobileViewport;
    window.categoryPriority = categoryPriority;
    window.constructionShiftPriority = constructionShiftPriority;
    window.compactCategoryClass = compactCategoryClass;
    window.detailLineCount = detailLineCount;
    window.detailInlineHtml = detailInlineHtml;
    window.renderCompactScheduleItem = renderCompactScheduleItem;
    window.renderMobileCalendar = renderMobileCalendar;
    window.renderDesktopCalendar = renderDesktopCalendar;
    window.bindCompactItemActions = bindCompactItemActions;
    window.getActiveScheduleCardId = getActiveScheduleCardId;
    window.restoreActiveScheduleCard = restoreActiveScheduleCard;
    window.openQuickAddForDate = openQuickAddForDate;
    window.submitQuickAddSchedule = submitQuickAddSchedule;
    window.openEditRequestById = openEditRequestById;
    window.submitDirectEdit = submitDirectEdit;
    window.requestDeleteById = requestDeleteById;
    window.statusBadgeClass = statusBadgeClass;
    window.nextStatus = nextStatus;
    window.saveWorkerStatusPatch = saveWorkerStatusPatch;
    window.handleWorkerStatusClick = handleWorkerStatusClick;
    window.handleWorkerLocationClick = handleWorkerLocationClick;
    window.autoFitWorkerLocationText = autoFitWorkerLocationText;
    window.openScheduleDetailModal = openScheduleDetailModal;
    window.openDetailPreviewModal = openDetailPreviewModal;
    window.loadWorkerStatus = loadWorkerStatus;
    window.attachConstructionAutocomplete = attachConstructionAutocomplete;
    window.handleDriveUpload = handleDriveUpload;
})();

async function handleDriveUpload(event, scheduleId) {
    const input = event.target;
    const files = input.files ? Array.from(input.files) : [];
    if (!files.length) return;
    const label = document.getElementById(`drive-upload-label-${scheduleId}`);
    const originalHtml = label ? label.innerHTML : '';
    let failed = 0;
    for (let i = 0; i < files.length; i++) {
        if (label) label.textContent = `업로드 중... (${i + 1}/${files.length})`;
        const formData = new FormData();
        formData.append('file', files[i]);
        try {
            const res = await fetch(`/api/schedules/${scheduleId}/drive-upload`, {
                method: 'POST', body: formData,
            });
            if (!res.ok) {
                const errText = await res.text().catch(() => '');
                if (typeof showSaveToast === 'function') showSaveToast(`업로드 실패 (${res.status})${errText ? ': ' + errText.slice(0, 80) : ''}`, 'error');
                failed++; continue;
            }
            const data = await res.json();
            if (data.link && typeof showSaveToast === 'function') {
                showSaveToast(`${files[i].name} 업로드 완료`, 'success');
            }
        } catch (err) {
            const msg = `업로드 오류: ${err.message || err}`;
            alert(msg);
            if (typeof showSaveToast === 'function') showSaveToast(msg, 'error');
            failed++;
        }
    }
    input.value = '';
    if (label) label.innerHTML = originalHtml;
    if (failed > 0 && typeof showSaveToast === 'function') {
        showSaveToast(`${failed}개 업로드 실패`, 'error');
    }
}

async function loadAttachmentFeed(scheduleId) {
    const feedEl = document.querySelector(`.schedule-attachment-feed[data-schedule-id="${scheduleId}"]`);
    if (!feedEl) return;
    const listEl = feedEl.querySelector('.attachment-feed-list');
    if (!listEl) return;
    listEl.innerHTML = '<span class="text-muted small">로딩 중...</span>';
    try {
        const res = await fetch(`/api/schedules/${scheduleId}/attachments`);
        if (!res.ok) { listEl.innerHTML = ''; return; }
        const data = await res.json();
        renderAttachmentFeed(listEl, data.attachments || [], scheduleId);
    } catch (_) {
        listEl.innerHTML = '';
    }
}

function renderAttachmentFeed(listEl, attachments, scheduleId) {
    if (!attachments.length) {
        listEl.innerHTML = '<span class="text-muted small" style="font-size:0.75rem">첨부된 파일이 없습니다.</span>';
        return;
    }
    const IMAGE_EXTS = new Set(['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.heic', '.heif']);
    listEl.innerHTML = attachments.map((att) => {
        const filePath = att.file_path || '';
        const ext = filePath.substring(filePath.lastIndexOf('.')).toLowerCase();
        const isImage = IMAGE_EXTS.has(ext);
        // file_path는 자동화_데이터/... 형태이므로 자동화_데이터/ 이후 경로를 URL에 사용
        const relPath = filePath.replace(/\\/g, '/').replace(/^자동화_데이터\//, '');
        const imgUrl = `/uploads/photos/${relPath}`;
        const timeStr = (att.created_at || '').substring(0, 16).replace('T', ' ');
        const noteHtml = att.note ? `<div class="attachment-note">${escapeHtml(att.note)}</div>` : '';
        const thumbHtml = isImage
            ? `<a href="${imgUrl}" target="_blank" onclick="event.stopPropagation()"><img src="${imgUrl}" class="attachment-thumb" alt="첨부 이미지" loading="lazy"></a>`
            : `<a href="${imgUrl}" target="_blank" class="attachment-file-link" onclick="event.stopPropagation()">📄 ${escapeHtml(filePath.split(/[/\\]/).pop())}</a>`;
        return `<div class="attachment-item">
            ${thumbHtml}
            <div class="attachment-meta">
                <span class="attachment-time">${escapeHtml(timeStr)}</span>
                ${noteHtml}
                <button class="btn btn-sm attachment-del-btn" title="삭제" onclick="event.stopPropagation(); deleteAttachment(${att.id}, ${scheduleId})">✕</button>
            </div>
        </div>`;
    }).join('');
}

async function handleAttachmentUpload(event, scheduleId) {
    const input = event.target;
    const files = input.files ? Array.from(input.files) : [];
    if (!files.length) return;
    const feedEl = document.querySelector(`.schedule-attachment-feed[data-schedule-id="${scheduleId}"]`);
    const label = feedEl ? feedEl.querySelector('.attachment-upload-label') : null;
    const resetLabel = () => {
        if (label) label.innerHTML = `사진/파일 추가<input type="file" accept="image/*,application/pdf" multiple style="display:none" onchange="event.stopPropagation(); handleAttachmentUpload(event, '${scheduleId}')">`;
    };
    if (label) label.textContent = `업로드 중... (0/${files.length})`;
    let failed = 0;
    for (let i = 0; i < files.length; i++) {
        if (label) label.textContent = `업로드 중... (${i + 1}/${files.length})`;
        const formData = new FormData();
        formData.append('file', files[i]);
        formData.append('upload_category', '첨부자료');
        formData.append('linked_schedule_id', String(scheduleId));
        try {
            const res = await fetch('/api/vision/upload', { method: 'POST', body: formData });
            if (!res.ok) failed++;
        } catch (_) {
            failed++;
        }
    }
    input.value = '';
    resetLabel();
    if (failed > 0 && typeof showSaveToast === 'function') {
        showSaveToast(`${failed}개 업로드 실패`, 'error');
    }
    await loadAttachmentFeed(scheduleId);
}

async function deleteAttachment(attachmentId, scheduleId) {
    if (!confirm('이 첨부 파일을 삭제하시겠습니까?')) return;
    try {
        const res = await fetch(`/api/schedules/${scheduleId}/attachments/${attachmentId}`, { method: 'DELETE' });
        if (!res.ok) {
            if (typeof showSaveToast === 'function') showSaveToast('삭제 실패', 'error');
            return;
        }
        await loadAttachmentFeed(scheduleId);
    } catch (_) {
        if (typeof showSaveToast === 'function') showSaveToast('삭제 중 오류가 발생했습니다.', 'error');
    }
}
