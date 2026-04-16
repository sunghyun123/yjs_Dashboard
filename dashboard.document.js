(function () {
    const HANGUL_GENERATOR_RELEASE_URL =
        'https://github.com/sunghyun123/yjs_automation_tool/releases/tag/v1.0.6';

    function getDocState() {
        if (!window.__dashboardDocState) {
            window.__dashboardDocState = {
                templatesCache: [],
                flowPurpose: '',
                genTemplateId: '',
                genTemplateMeta: null,
                extractTemplateId: '',
                extractLastValues: {},
                extractIsTable: false,
            };
        }
        return window.__dashboardDocState;
    }

    function getTemplateById(templateId) {
        const state = getDocState();
        return state.templatesCache.find((x) => String(x.id) === String(templateId));
    }

    async function downloadResponseBlob(res, fallbackFilename = 'document') {
        const blob = await res.blob();
        let filename = fallbackFilename;
        const cd = res.headers.get('Content-Disposition') || '';
        const m = cd.match(/filename="?([^";]+)"?/i);
        if (m) filename = m[1];
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    }

    function openHangulGeneratorDownload() {
        window.open(HANGUL_GENERATOR_RELEASE_URL, '_blank', 'noopener,noreferrer');
    }

    async function launchLocalApp(appKey) {
        try {
            const res = await fetch('/api/local/launch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ app: appKey }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                alert(data.detail || '실행에 실패했습니다. 서버 PC의 .env에 LOCAL_APPS_ROOT와 exe 파일명을 확인하세요.');
                return;
            }
            showSaveToast(data.message || '실행 요청 완료', 'success');
            toggleAppDrawer(false);
        } catch (e) {
            alert('실행 요청 중 오류가 발생했습니다.');
        }
    }

    async function openDocumentTemplatePicker(purpose) {
        const state = getDocState();
        state.flowPurpose = purpose;
        toggleAppDrawer(false);
        document.getElementById('documentTemplateModalTitle').textContent =
            purpose === 'generate' ? '문서 생성 — 템플릿 선택' : '문서 추출 — 템플릿 선택';
        const listEl = document.getElementById('documentTemplateList');
        listEl.innerHTML = '<div class="text-muted small p-2">불러오는 중…</div>';
        window.documentTemplateModal.show();
        try {
            const res = await fetch('/api/documents/templates');
            const data = await res.json();
            if (!res.ok) {
                listEl.innerHTML = `<div class="text-danger small p-2">${escapeHtml(data.detail || '목록을 불러오지 못했습니다.')}</div>`;
                return;
            }
            state.templatesCache = Array.isArray(data.templates) ? data.templates : [];
            const pickList =
                state.flowPurpose === 'generate'
                    ? state.templatesCache.filter((t) => t.generate_enabled !== false)
                    : state.templatesCache.filter((t) => t.extract_enabled !== false);
            if (!pickList.length) {
                listEl.innerHTML =
                    '<div class="small text-muted p-2">이 작업에서 사용할 수 있는 템플릿이 없습니다. templates.json의 generate_enabled / extract_enabled 설정을 확인하세요.</div>';
                return;
            }
            listEl.innerHTML = pickList
                .map(
                    (t) =>
                        `<button type="button" class="list-group-item list-group-item-action" data-doc-tpl="${escapeHtml(t.id)}"><strong>${escapeHtml(t.title || t.id)}</strong><div class="small text-muted">${escapeHtml(t.kind || '')}${t.extract_mode === 'table' ? ' · 표 추출' : ''}${t.generate_enabled === false ? ' · 생성 비활성' : ''}${t.extract_enabled === false ? ' · 추출 비활성' : ''}</div></button>`
                )
                .join('');
            listEl.querySelectorAll('[data-doc-tpl]').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const id = btn.getAttribute('data-doc-tpl');
                    window.documentTemplateModal.hide();
                    if (state.flowPurpose === 'generate') openDocumentGenerate(id);
                    else openDocumentExtract(id);
                });
            });
        } catch (e) {
            listEl.innerHTML = '<div class="text-danger small p-2">네트워크 오류</div>';
        }
    }

    function validateDocGenRequiredGate() {
        const state = getDocState();
        const t = state.genTemplateMeta;
        if (!t) return true;
        const req = Array.isArray(t.required_gate) ? t.required_gate : [];
        for (const key of req) {
            const el = document.querySelector(`#docGenFields [data-doc-field="${key}"]`);
            if (!el || !String(el.value || '').trim()) {
                alert(`다음 필수 항목을 선택하거나 입력해 주세요: ${key}`);
                return false;
            }
        }
        return true;
    }

    function openDocumentGenerate(templateId) {
        const state = getDocState();
        const t = getTemplateById(templateId);
        if (!t) {
            alert('템플릿을 찾을 수 없습니다.');
            return;
        }
        state.genTemplateId = String(templateId);
        state.genTemplateMeta = t;
        document.getElementById('docGenContext').value = '';
        const box = document.getElementById('docGenFields');
        const fields = Array.isArray(t.fields) ? t.fields : [];
        const req = Array.isArray(t.required_gate) ? t.required_gate : [];
        box.innerHTML = fields
            .map((f) => {
                const id = escapeHtml(f.id);
                const lab = escapeHtml(f.label || f.id);
                const hint = f.ai_recommend ? '<span class="text-primary small">(AI 추천 가능)</span>' : '';
                const reqMark = req.includes(String(f.id)) ? ' <span class="text-danger small">*</span>' : '';
                const opts = Array.isArray(f.options) ? f.options : [];
                if (opts.length) {
                    const optHtml = opts
                        .map(
                            (o) =>
                                `<option value="${escapeHtml(String(o.value))}">${escapeHtml(
                                    o.label != null ? String(o.label) : String(o.value)
                                )}</option>`
                        )
                        .join('');
                    return `<label class="form-label small mb-0">${lab}${reqMark} ${hint}</label><select class="form-select form-select-sm mb-2" data-doc-field="${id}"><option value="">선택…</option>${optHtml}</select>`;
                }
                return `<label class="form-label small mb-0">${lab}${reqMark} ${hint}</label><input class="form-control form-control-sm mb-2" data-doc-field="${id}" />`;
            })
            .join('');
        window.documentGenerateModal.show();
    }

    async function runDocumentSuggest() {
        const state = getDocState();
        if (!state.genTemplateId) return;
        if (!validateDocGenRequiredGate()) return;
        try {
            const res = await fetch('/api/documents/suggest', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    template_id: state.genTemplateId,
                    context_text: document.getElementById('docGenContext').value.trim() || null,
                    values: collectDocGenValues(),
                }),
            });
            const data = await res.json();
            if (!res.ok) {
                alert(data.detail || 'AI 추천에 실패했습니다.');
                return;
            }
            const vals = data.values || {};
            document.querySelectorAll('#docGenFields [data-doc-field]').forEach((inp) => {
                const id = inp.getAttribute('data-doc-field');
                if (vals[id] != null && String(vals[id]).trim() !== '') inp.value = vals[id];
            });
            showSaveToast('추천 값을 반영했습니다. 필요하면 수정하세요.', 'info');
        } catch (e) {
            alert('AI 추천 요청 중 오류가 발생했습니다.');
        }
    }

    function collectDocGenValues() {
        const values = {};
        document.querySelectorAll('#docGenFields [data-doc-field]').forEach((inp) => {
            values[inp.getAttribute('data-doc-field')] = inp.value;
        });
        return values;
    }

    async function downloadFilledDocument() {
        const state = getDocState();
        if (!state.genTemplateId) return;
        if (!validateDocGenRequiredGate()) return;
        try {
            const res = await fetch('/api/documents/fill', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ template_id: state.genTemplateId, values: collectDocGenValues() }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                alert(err.detail || '파일 생성에 실패했습니다.');
                return;
            }
            await downloadResponseBlob(res);
            showSaveToast('다운로드를 시작했습니다.', 'success');
            window.documentGenerateModal.hide();
        } catch (e) {
            alert('다운로드 중 오류가 발생했습니다.');
        }
    }

    function openDocumentExtract(templateId) {
        const state = getDocState();
        state.extractTemplateId = String(templateId);
        state.extractLastValues = {};
        state.extractIsTable = false;
        document.getElementById('docExtractFile').value = '';
        document.getElementById('docExtractUploadSection').style.display = 'block';
        document.getElementById('docExtractReviewSection').style.display = 'none';
        document.getElementById('docExtractDropZone').textContent = '📷 이미지 선택 / 드래그';
        const boardBtn = document.getElementById('docExtractBoardBtn');
        if (boardBtn) boardBtn.classList.add('d-none');
        window.documentExtractModal.show();
    }

    function markDocExtractFileSelected() {
        const f = document.getElementById('docExtractFile').files[0];
        const z = document.getElementById('docExtractDropZone');
        z.textContent = f ? `선택됨: ${f.name}` : '📷 이미지 선택 / 드래그';
    }

    function setupDocumentExtractDropzone() {
        const z = document.getElementById('docExtractDropZone');
        const input = document.getElementById('docExtractFile');
        if (!z || z.dataset.bound === '1') return;
        z.dataset.bound = '1';
        ['dragenter', 'dragover'].forEach((ev) => {
            z.addEventListener(ev, (e) => {
                e.preventDefault();
                e.stopPropagation();
                z.classList.add('dragover');
            });
        });
        ['dragleave', 'drop'].forEach((ev) => {
            z.addEventListener(ev, (e) => {
                e.preventDefault();
                e.stopPropagation();
                z.classList.remove('dragover');
            });
        });
        z.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            if (files && files[0]) {
                input.files = files;
                markDocExtractFileSelected();
            }
        });
    }

    async function submitDocumentExtract() {
        const state = getDocState();
        const f = document.getElementById('docExtractFile').files[0];
        if (!f) {
            alert('이미지를 선택해 주세요.');
            return;
        }
        if (!state.extractTemplateId) return;
        const runBtn = document.getElementById('docExtractRunBtn');
        if (runBtn && runBtn.disabled) return;
        const fd = new FormData();
        fd.append('template_id', state.extractTemplateId);
        fd.append('file', f);
        const ac = new AbortController();
        const timeoutMs = 45000;
        const timeoutId = setTimeout(() => ac.abort(), timeoutMs);
        try {
            if (runBtn) {
                runBtn.disabled = true;
                runBtn.textContent = 'AI 추출 중...';
            }
            showSaveToast('이미지 분석 중…', 'info');
            const res = await fetch('/api/documents/extract', {
                method: 'POST',
                body: fd,
                signal: ac.signal,
            });
            const data = await res.json();
            if (!res.ok) {
                alert(data.detail || '추출에 실패했습니다.');
                return;
            }
            state.extractIsTable = data.extract_mode === 'table';
            state.extractLastValues = data.values || {};
            const boardBtn = document.getElementById('docExtractBoardBtn');
            if (state.extractIsTable) {
                renderDocExtractTableReview(data.rows || [], state.extractLastValues);
                const btn = document.getElementById('docExtractConfirmBtn');
                const hint = document.getElementById('docExtractReviewHint');
                if (btn) btn.textContent = '엑셀 다운로드';
                if (state.extractTemplateId === 'construction_schedule_xlsx') {
                    if (boardBtn) boardBtn.classList.remove('d-none');
                    if (hint) {
                        hint.textContent =
                            '행을 수정한 뒤 엑셀로 받거나, 녹색 버튼으로 상황판(공사 일정)에 반영할 수 있습니다.';
                    }
                } else {
                    if (boardBtn) boardBtn.classList.add('d-none');
                    if (hint) {
                        hint.textContent =
                            '표 셀을 직접 수정한 뒤 엑셀을 받습니다. 빈 행은 저장 시 자동으로 제외됩니다.';
                    }
                }
            } else {
                if (boardBtn) boardBtn.classList.add('d-none');
                renderDocExtractReviewForm(state.extractLastValues);
                const btn = document.getElementById('docExtractConfirmBtn');
                const hint = document.getElementById('docExtractReviewHint');
                if (btn) btn.textContent = '파일 받기';
                if (hint) {
                    hint.textContent =
                        '틀린 부분을 고친 뒤 아래 버튼으로 파일을 받습니다. (표 추출은 엑셀, 일반 템플릿은 등록된 형식으로 저장됩니다.)';
                }
            }
            document.getElementById('docExtractUploadSection').style.display = 'none';
            document.getElementById('docExtractReviewSection').style.display = 'block';
        } catch (e) {
            if (e && e.name === 'AbortError') {
                alert('AI 추출이 지연되어 요청을 중단했습니다. 이미지 해상도를 줄이거나 다시 시도해 주세요.');
            } else {
                alert('추출 요청 중 오류가 발생했습니다.');
            }
        } finally {
            clearTimeout(timeoutId);
            if (runBtn) {
                runBtn.disabled = false;
                runBtn.textContent = 'AI 추출 실행';
            }
        }
    }

    function resetDocumentExtractFlow() {
        const state = getDocState();
        document.getElementById('docExtractUploadSection').style.display = 'block';
        document.getElementById('docExtractReviewSection').style.display = 'none';
        document.getElementById('docExtractFile').value = '';
        document.getElementById('docExtractDropZone').textContent = '📷 이미지 선택 / 드래그';
        state.extractLastValues = {};
        state.extractIsTable = false;
        document.getElementById('docExtractReviewList').innerHTML = '';
        const boardBtn = document.getElementById('docExtractBoardBtn');
        if (boardBtn) boardBtn.classList.add('d-none');
        const btn = document.getElementById('docExtractConfirmBtn');
        const hint = document.getElementById('docExtractReviewHint');
        if (btn) btn.textContent = '파일 받기';
        if (hint) {
            hint.textContent =
                '틀린 부분을 고친 뒤 아래 버튼으로 파일을 받습니다. (표 추출은 엑셀, 일반 템플릿은 등록된 형식으로 저장됩니다.)';
        }
    }

    function normalizePlanDateInput(raw) {
        const t = String(raw || '').trim();
        if (!t) return '';
        let m = /^(\d{4})-(\d{2})-(\d{2})/.exec(t);
        if (m) return `${m[1]}-${m[2]}-${m[3]}`;
        m = /(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일/.exec(t);
        if (m) {
            const y = m[1];
            const mo = String(m[2]).padStart(2, '0');
            const day = String(m[3]).padStart(2, '0');
            return `${y}-${mo}-${day}`;
        }
        return '';
    }

    async function confirmExtractedPlanToBoard() {
        const state = getDocState();
        if (state.extractTemplateId !== 'construction_schedule_xlsx') return;
        const values = collectDocExtractReviewValues();
        const dateRaw = (values.constuction_time || '').trim();
        const date = normalizePlanDateInput(dateRaw);
        if (!date) {
            alert(
                '작업일자를 입력해 주세요. (예: 2026-04-16 또는 2026년 4월 16일)\n상단 "작업일자" 칸을 확인하세요.'
            );
            return;
        }
        const rows = collectDocExtractTableRows().filter((r) => String(r.task || '').trim());
        if (!rows.length) {
            alert('반영할 공사 일정(추출 행)이 없습니다. task 열이 비어 있지 않은지 확인하세요.');
            return;
        }
        try {
            const res = await fetch('/api/schedules/import-construction-plan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ date, rows }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                alert(data.detail || '상황판 반영에 실패했습니다.');
                return;
            }
            if (Array.isArray(data.overlap_warnings) && data.overlap_warnings.length) {
                showSaveToast(
                    `${data.message || '등록했습니다.'} 유사한 기존 일정이 ${data.overlap_warnings.length}건 있어 확인해 주세요.`,
                    'warning'
                );
            } else {
                showSaveToast(data.message || '상황판에 반영했습니다.', 'success');
            }
            if (typeof window.loadSchedules === 'function') {
                window.loadSchedules();
            }
            window.documentExtractModal.hide();
        } catch (_e) {
            alert('상황판 반영 중 오류가 발생했습니다.');
        }
    }

    function renderDocExtractTableReview(rows, values = {}) {
        const state = getDocState();
        const t = getTemplateById(state.extractTemplateId);
        const cols = (t && t.table_columns) || [];
        const fields = (t && t.fields) || [];
        const box = document.getElementById('docExtractReviewList');
        if (!cols.length) {
            box.innerHTML = '<div class="text-muted">열 정의(table_columns)가 없습니다.</div>';
            return;
        }
        const data = Array.isArray(rows) && rows.length ? rows : [{}];
        const thead =
            '<thead><tr>' +
            cols.map((c) => `<th class="small text-nowrap">${escapeHtml(c.header || c.id)}</th>`).join('') +
            '</tr></thead>';
        const tbody =
            '<tbody>' +
            data
                .map((row, ri) => {
                    const cells = cols
                        .map((c) => {
                            const v = row[c.id] != null ? String(row[c.id]) : '';
                            const safeId = escapeHtml(c.id);
                            const safeVal = escapeHtml(v);
                            return `<td class="p-0 align-middle"><input type="text" class="form-control form-control-sm border-0 rounded-0" style="min-width:4.5rem" data-trow="${ri}" data-tcol="${safeId}" value="${safeVal}" /></td>`;
                        })
                        .join('');
                    return `<tr>${cells}</tr>`;
                })
                .join('') +
            '</tbody>';
        const headerFieldsHtml = fields.length
            ? `<div class="border rounded p-2 bg-light mb-3">${fields
                .map((field) => {
                    const fid = String(field.id);
                    const raw = values[fid];
                    const val = raw != null ? String(raw) : '';
                    return `<div class="mb-2">
                        <label class="form-label small mb-1 fw-semibold">${escapeHtml(field.label || field.id)}</label>
                        <input type="text" class="form-control form-control-sm" data-doc-extract-field="${escapeHtml(
                            fid
                        )}" value="${escapeHtml(val)}" />
                    </div>`;
                })
                .join('')}</div>`
            : '';
        box.innerHTML = `${headerFieldsHtml}<div class="table-responsive" style="max-height: 360px; overflow: auto;"><table class="table table-sm table-bordered align-middle mb-0">${thead}${tbody}</table></div>`;
    }

    function collectDocExtractTableRows() {
        const state = getDocState();
        const t = getTemplateById(state.extractTemplateId);
        const cols = (t && t.table_columns) || [];
        const tbody = document.querySelector('#docExtractReviewList tbody');
        if (!tbody || !cols.length) return [];
        const out = [];
        tbody.querySelectorAll('tr').forEach((tr) => {
            const obj = {};
            cols.forEach((c) => {
                const inp = tr.querySelector(`input[data-tcol="${c.id}"]`);
                obj[c.id] = inp ? inp.value.trim() : '';
            });
            out.push(obj);
        });
        return out;
    }

    function renderDocExtractReviewForm(values) {
        const state = getDocState();
        const t = getTemplateById(state.extractTemplateId);
        const fields = (t && t.fields) || [];
        const box = document.getElementById('docExtractReviewList');
        if (!fields.length) {
            box.innerHTML = '<div class="text-muted">표시할 필드가 없습니다.</div>';
            return;
        }
        box.innerHTML = fields
            .map((field) => {
                const fid = String(field.id);
                const raw = values[fid];
                const val = raw != null ? String(raw) : '';
                const safeLabel = escapeHtml(field.label || field.id);
                const safeVal = escapeHtml(val);
                return `<div class="mb-3">
                        <label class="form-label small mb-1 fw-semibold">${safeLabel}</label>
                        <textarea class="form-control form-control-sm" rows="2" data-doc-extract-field="${escapeHtml(fid)}">${safeVal}</textarea>
                    </div>`;
            })
            .join('');
    }

    function collectDocExtractReviewValues() {
        const out = {};
        document.querySelectorAll('#docExtractReviewList [data-doc-extract-field]').forEach((el) => {
            const fid = el.getAttribute('data-doc-extract-field');
            if (fid) out[fid] = el.value.trim();
        });
        return out;
    }

    async function confirmExtractedDocumentExport() {
        const state = getDocState();
        if (!state.extractTemplateId) return;
        try {
            let res;
            if (state.extractIsTable) {
                const rows = collectDocExtractTableRows();
                const values = collectDocExtractReviewValues();
                res = await fetch('/api/documents/export-table', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ template_id: state.extractTemplateId, rows, values }),
                });
            } else {
                const values = collectDocExtractReviewValues();
                res = await fetch('/api/documents/fill', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ template_id: state.extractTemplateId, values }),
                });
            }
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                alert(err.detail || '문서 생성에 실패했습니다.');
                return;
            }
            await downloadResponseBlob(res);
            showSaveToast('다운로드를 시작했습니다.', 'success');
            window.documentExtractModal.hide();
        } catch (e) {
            alert('다운로드 중 오류가 발생했습니다.');
        }
    }

    window.openHangulGeneratorDownload = openHangulGeneratorDownload;
    window.launchLocalApp = launchLocalApp;
    window.openDocumentTemplatePicker = openDocumentTemplatePicker;
    window.validateDocGenRequiredGate = validateDocGenRequiredGate;
    window.openDocumentGenerate = openDocumentGenerate;
    window.runDocumentSuggest = runDocumentSuggest;
    window.collectDocGenValues = collectDocGenValues;
    window.downloadFilledDocument = downloadFilledDocument;
    window.openDocumentExtract = openDocumentExtract;
    window.markDocExtractFileSelected = markDocExtractFileSelected;
    window.setupDocumentExtractDropzone = setupDocumentExtractDropzone;
    window.submitDocumentExtract = submitDocumentExtract;
    window.resetDocumentExtractFlow = resetDocumentExtractFlow;
    window.renderDocExtractTableReview = renderDocExtractTableReview;
    window.collectDocExtractTableRows = collectDocExtractTableRows;
    window.renderDocExtractReviewForm = renderDocExtractReviewForm;
    window.collectDocExtractReviewValues = collectDocExtractReviewValues;
    window.confirmExtractedDocumentExport = confirmExtractedDocumentExport;
    window.confirmExtractedPlanToBoard = confirmExtractedPlanToBoard;
})();
