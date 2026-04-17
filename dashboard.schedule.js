(function () {
    const DAY_COLLAPSE_LIMIT = 4;
    const quickAddSelectedPersonNames = new Set();

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
                alert(data.detail || '처리에 실패했습니다.');
                return;
            }
            if (typeof showSaveToast === 'function') {
                showSaveToast(data.message || '검토 완료로 표시했습니다.', 'success');
            }
            await loadSchedules();
        } catch (_e) {
            alert('요청 중 오류가 발생했습니다.');
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

    async function loadSchedules() {
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
        const personLine = fullPersonLabel(item.person);
        const detailLine = String(item.details || '').trim();
        const detailLines = detailLineCount(detailLine);
        const shiftType = applyDefaultShiftType(item.category || '', item.shift_type || '');
        const shiftClass = shiftBadgeClass(shiftType);
        const workCode = String(item.work_code || '').trim();
        const taskLabel = `${escapeHtml(displayScheduleTaskTitle(item.task) || '공사명 미기재')}`;
        const badgeParts = [];
        if (shiftType) badgeParts.push(`<span class="schedule-shift-badge ${shiftClass}">${shiftType}</span>`);
        if (scheduleViewOptions.showWorkCode && workCode) {
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
        const detailModalBtn = detailLine && detailLines >= 3
            ? `<button type="button" class="btn btn-sm btn-outline-dark mt-1" onclick="event.stopPropagation(); openScheduleDetailModal('${item.id}')">상세 정보</button>`
            : '';
        return `
                <div class="schedule-compact-item ${catClass} ${shiftCardClass}${photoPlanClass}" data-id="${item.id}">
                    <div class="schedule-compact-task"><span class="schedule-task-head"><span class="schedule-category-dot ${catClass}"></span>${taskLabel}</span>${badgesHtml}</div>
                    ${scheduleViewOptions.showPerson && personLine ? `<div class="schedule-compact-person">👷 ${escapeHtml(personLine)}</div>` : ''}
                    ${scheduleViewOptions.showDetails && detailLine ? `<div class="schedule-compact-detail-preview">📝 ${escapeHtml(detailLine)}</div>` : ''}
                    <div class="schedule-action-panel">
                        ${detailLine && detailLines <= 2 ? `<div class="detail-text">📝 ${detailInlineHtml(detailLine)}</div>` : ''}
                        ${detailModalBtn}
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
            if (e.target.closest('button') || e.target.closest('input') || e.target.closest('textarea')) return;
            document.querySelectorAll('.schedule-compact-item.active').forEach((el) => {
                if (el !== card) el.classList.remove('active');
            });
            card.classList.toggle('active');
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
        if (target) target.classList.add('active');
    }

    function openEditRequestById(scheduleId) {
        const item = scheduleMap.get(String(scheduleId));
        if (!item) {
            alert('일정 정보를 찾을 수 없습니다. 새로고침 후 다시 시도하세요.');
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
        const advancedSection = document.getElementById('quickAddAdvancedSection');
        const staffListBox = document.getElementById('quickAddFieldStaffList');
        if (!dateInput || !window.quickAddScheduleModal) return;
        quickAddSelectedPersonNames.clear();
        bindQuickAddSectionEvents();
        if (peopleSection) peopleSection.open = false;
        if (advancedSection) advancedSection.open = false;
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
            alert('작업/메모 제목을 입력하세요.');
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
        };
        const response = await fetch('/api/schedules/board/template-action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            alert(data.detail || '일정 등록에 실패했습니다.');
            return;
        }
        if (window.quickAddScheduleModal) window.quickAddScheduleModal.hide();
        if (typeof showSaveToast === 'function') {
            showSaveToast(data.message || '일정을 등록했습니다.', 'success');
        }
        await loadSchedules();
    }

    async function submitDirectEdit() {
        const scheduleId = Number(document.getElementById('editScheduleId').value);
        if (!scheduleId) {
            alert('수정 대상 일정 ID가 없습니다.');
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
            }
        };

        if (!payload.schedule_data.task) {
            alert('공사명·작업 내용(task)은 필수입니다.');
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
            alert(result.detail || result.message || '수정 실패');
            return;
        }
        window.editRequestModal.hide();
        alert(result.message || '수정되었습니다.');
        await loadSchedules();
    }

    async function requestDeleteById(scheduleId) {
        const item = scheduleMap.get(String(scheduleId));
        if (!item) {
            alert('일정 정보를 찾을 수 없습니다. 새로고침 후 다시 시도하세요.');
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
            alert(result.detail || result.message || '삭제 실패');
            return;
        }
        alert(result.message || '삭제되었습니다.');
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
            alert(data.detail || '상태 저장 실패');
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
            const metaInner = workerExpanded && row.status === '외출'
                ? `<button type="button" class="btn btn-link btn-sm p-0 text-decoration-none text-muted worker-location-btn" onclick="handleWorkerLocationClick('${encodeURIComponent(row.user_name)}','${encodeURIComponent(row.location || '')}')">${escapeHtml(row.location || '행선 입력')}</button>`
                : '';
            return `
                <li class="list-group-item d-flex justify-content-between align-items-center py-2 gap-1">
                    <b class="worker-row-name text-truncate mb-0 min-w-0" style="max-width: 48%;">${escapeHtml(row.user_name)}</b>
                    <div class="d-flex align-items-center justify-content-end gap-1 flex-shrink-0 flex-grow-1" style="min-width: 0;">
                        <button type="button" class="btn btn-sm badge status-badge-sm ${statusBadgeClass(row.status)}" onclick="handleWorkerStatusClick('${encodeURIComponent(row.user_name)}','${encodeURIComponent(row.status || '사무실')}')">${statusLabelText(row.status)}</button>
                        <span class="text-muted small worker-outing-meta text-end">${metaInner}</span>
                    </div>
                </li>
            `;
        }).join('');
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
})();
