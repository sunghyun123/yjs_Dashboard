(function () {
    'use strict';

    // 담당자별 핀 색상/약칭 (home.js와 동일)
    const MANAGER_STYLE = {
        '김무선': { color: '#2f6fed', short: '무선' },
        '김상훈': { color: '#e8590c', short: '상훈' },
        '이재규': { color: '#2f9e44', short: '이재' },
        '김단후': { color: '#ae3ec9', short: '단후' },
    };
    const DEFAULT_STYLE = { color: '#64748b', short: '담당' };
    const ANYANG_CENTER = { lat: 37.3943, lng: 126.9568 };

    let kakaoKey = '';
    let map = null;
    let geocoder = null;
    let places = null;
    let mapReady = false;

    let rows = [];               // { _id, no, name, manager, percent, addr, lat, lng, pinned }
    const markerMap = {};        // _id -> kakao.maps.Marker
    let pickRowId = null;        // 📍 위치 지정 대기 중인 행
    let seq = 1;

    const $ = (id) => document.getElementById(id);
    const uid = () => 'r' + (seq++);

    function managerStyle(name) {
        return MANAGER_STYLE[String(name || '').trim()] || DEFAULT_STYLE;
    }

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function banner(msg, type) {
        const el = $('banner');
        el.className = 'alert m-0 rounded-0 py-2 px-3 alert-' + (type || 'info');
        el.textContent = msg;
        el.classList.remove('d-none');
        if (type === 'success') {
            setTimeout(() => el.classList.add('d-none'), 5000);
        }
    }

    function setRowInfo() {
        const named = rows.filter((r) => String(r.name || '').trim()).length;
        const pinned = rows.filter((r) => r.pinned).length;
        $('rowInfo').textContent = `총 ${named}건 · 위치 지정 ${pinned}건`;
    }

    // ── 좌표 후보(주소 우선, 없으면 공사명 추출) — home.js와 동일 휴리스틱 ──
    function buildGeocodeQueries(name) {
        const raw = String(name || '').replace(/_\d+\b/g, ' ').replace(/\([^)]*\)/g, ' ').trim();
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
        const jibun = raw.match(/([가-힣]+(?:동|리|가))\s*(\d+(?:-\d+)?)/);
        if (jibun) {
            push('address', `${jibun[1]} ${jibun[2]}`);
            push('keyword', `${jibun[1]} ${jibun[2]}`);
        }
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
        const dong = raw.match(/[가-힣]+동/);
        if (dong) push('keyword', dong[0]);
        return out;
    }

    function buildQueriesForItem(item) {
        const addr = String((item && item.addr) || '').trim();
        const out = [];
        if (addr) {
            out.push({ mode: 'address', query: addr });
            out.push({ mode: 'keyword', query: addr });
        }
        return out.concat(buildGeocodeQueries(item.name));
    }

    function geocodeQueries(queries) {
        const centerLatLng = new kakao.maps.LatLng(ANYANG_CENTER.lat, ANYANG_CENTER.lng);
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

    // ── 마커 ──
    function pinImageSrc(style) {
        const svg =
            `<svg xmlns='http://www.w3.org/2000/svg' width='40' height='48' viewBox='0 0 40 48'>` +
            `<path d='M20 47C20 47 36 28 36 16.5A16 16 0 1 0 4 16.5C4 28 20 47 20 47Z' fill='${style.color}' stroke='#ffffff' stroke-width='2.5'/>` +
            `<text x='20' y='21' text-anchor='middle' font-family='Malgun Gothic,sans-serif' font-size='11' font-weight='700' fill='#ffffff'>${style.short}</text>` +
            `</svg>`;
        return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
    }

    function removeMarker(id) {
        if (markerMap[id]) {
            markerMap[id].setMap(null);
            delete markerMap[id];
        }
    }

    function clearMarkers() {
        Object.keys(markerMap).forEach(removeMarker);
    }

    function placeMarker(r, coord) {
        removeMarker(r._id);
        const style = managerStyle(r.manager);
        const image = new kakao.maps.MarkerImage(
            pinImageSrc(style),
            new kakao.maps.Size(40, 48),
            { offset: new kakao.maps.Point(20, 47) }
        );
        const marker = new kakao.maps.Marker({
            position: new kakao.maps.LatLng(coord.lat, coord.lng),
            image,
            draggable: true,
            title: r.name,
            map,
        });
        kakao.maps.event.addListener(marker, 'dragend', () => {
            const p = marker.getPosition();
            r.lat = p.getLat();
            r.lng = p.getLng();
            r.pinned = true;
            refreshStatus(r);
            setRowInfo();
        });
        markerMap[r._id] = marker;
    }

    // ── 표 ──
    function statusBadge(r) {
        if (r.pinned) return '<span class="badge text-bg-success st-badge">지정됨</span>';
        if (String(r.addr || '').trim()) return '<span class="badge text-bg-light border st-badge">주소 자동</span>';
        return '<span class="badge text-bg-light border st-badge">이름 자동</span>';
    }

    function refreshStatus(r) {
        const cell = $('st-' + r._id);
        if (cell) cell.innerHTML = statusBadge(r);
    }

    function renderTable() {
        const tb = $('rowsBody');
        tb.innerHTML = rows.map((r, i) => (
            `<tr data-id="${r._id}">` +
            `<td class="text-muted">${i + 1}</td>` +
            `<td><input class="form-control form-control-sm" data-f="no" value="${esc(r.no)}"></td>` +
            `<td><input class="form-control form-control-sm" data-f="name" value="${esc(r.name)}"></td>` +
            `<td><input class="form-control form-control-sm" data-f="manager" list="managerList" value="${esc(r.manager)}"></td>` +
            `<td><input type="number" step="0.1" class="form-control form-control-sm" data-f="percent" value="${r.percent != null ? r.percent : 0}"></td>` +
            `<td><input class="form-control form-control-sm" data-f="addr" value="${esc(r.addr)}" placeholder="동 + 번지"></td>` +
            `<td id="st-${r._id}">${statusBadge(r)}</td>` +
            `<td class="text-nowrap">` +
            `<button class="btn btn-sm btn-outline-primary" data-act="pick" title="지도에서 위치 지정">📍</button> ` +
            `<button class="btn btn-sm btn-outline-danger" data-act="del" title="삭제">🗑</button>` +
            `</td>` +
            `</tr>`
        )).join('');
        setRowInfo();
    }

    function findRow(id) { return rows.find((r) => r._id === id); }

    function onBodyInput(e) {
        const input = e.target.closest('input[data-f]');
        if (!input) return;
        const tr = input.closest('tr');
        const r = findRow(tr && tr.dataset.id);
        if (!r) return;
        const f = input.dataset.f;
        if (f === 'percent') {
            r.percent = input.value === '' ? 0 : Number(input.value);
        } else {
            r[f] = input.value;
            if (f === 'manager' && markerMap[r._id]) {
                // 담당자 바뀌면 핀 색도 갱신
                placeMarker(r, { lat: r.lat, lng: r.lng });
            }
            if (f === 'addr') refreshStatus(r);
        }
    }

    function onBodyClick(e) {
        const btn = e.target.closest('button[data-act]');
        if (!btn) return;
        const tr = btn.closest('tr');
        const r = findRow(tr && tr.dataset.id);
        if (!r) return;
        if (btn.dataset.act === 'del') {
            removeMarker(r._id);
            rows = rows.filter((x) => x._id !== r._id);
            renderTable();
            return;
        }
        if (btn.dataset.act === 'pick') {
            enterPick(r._id, tr);
        }
    }

    function enterPick(id, tr) {
        exitPick();
        pickRowId = id;
        if (tr) tr.classList.add('pick-active');
        banner('지도를 클릭해 위치를 지정하세요. (취소: 다른 곳 작업)', 'info');
    }

    function exitPick() {
        if (pickRowId) {
            const tr = document.querySelector(`tr[data-id="${pickRowId}"]`);
            if (tr) tr.classList.remove('pick-active');
        }
        pickRowId = null;
    }

    // ── 카카오 지도 로딩 ──
    async function fetchKey() {
        try {
            const res = await fetch('/api/public-config');
            if (res.ok) {
                const cfg = await res.json();
                kakaoKey = cfg.kakaoMapJsKey || '';
            }
        } catch (_e) { /* noop */ }
    }

    function loadSdk() {
        return new Promise((resolve, reject) => {
            if (window.kakao && window.kakao.maps) { resolve(); return; }
            const s = document.createElement('script');
            s.id = 'kakao-maps-sdk';
            s.async = true;
            s.src = `//dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(kakaoKey)}&autoload=false&libraries=services`;
            s.addEventListener('load', () => resolve());
            s.addEventListener('error', () => reject(new Error('sdk load error')));
            document.head.appendChild(s);
        });
    }

    async function ensureMap() {
        if (mapReady) return true;
        await fetchKey();
        if (!kakaoKey) {
            banner('카카오맵 JS 키가 설정되지 않았습니다(서버 .env KAKAO_MAP_JS_KEY).', 'warning');
            return false;
        }
        try {
            await loadSdk();
        } catch (_e) {
            banner('카카오맵 SDK 로드 실패 — JS 키/도메인 등록을 확인하세요.', 'danger');
            return false;
        }
        await new Promise((resolve) => kakao.maps.load(resolve));
        map = new kakao.maps.Map($('adminMap'), {
            center: new kakao.maps.LatLng(ANYANG_CENTER.lat, ANYANG_CENTER.lng),
            level: 7,
        });
        map.setMaxLevel(12);
        geocoder = new kakao.maps.services.Geocoder();
        places = new kakao.maps.services.Places();
        kakao.maps.event.addListener(map, 'click', (e) => {
            if (!pickRowId) return;
            const r = findRow(pickRowId);
            const ll = e.latLng;
            if (r) {
                r.lat = ll.getLat();
                r.lng = ll.getLng();
                r.pinned = true;
                placeMarker(r, { lat: r.lat, lng: r.lng });
                refreshStatus(r);
                setRowInfo();
                banner('위치를 지정했습니다.', 'success');
            }
            exitPick();
        });
        mapReady = true;
        return true;
    }

    async function preview() {
        const ok = await ensureMap();
        if (!ok) return;
        clearMarkers();
        const bounds = new kakao.maps.LatLngBounds();
        let placed = 0;
        const failed = [];
        for (const r of rows) {
            if (!String(r.name || '').trim()) continue;
            let coord = null;
            if (r.lat != null && r.lng != null) {
                coord = { lat: r.lat, lng: r.lng };
            } else {
                coord = await geocodeQueries(buildQueriesForItem(r));
                if (coord) { r.lat = coord.lat; r.lng = coord.lng; }  // 표시는 하되 pinned는 false 유지
            }
            if (!coord) { failed.push(r.name); continue; }
            placeMarker(r, coord);
            bounds.extend(new kakao.maps.LatLng(coord.lat, coord.lng));
            placed++;
        }
        if (placed > 0) map.setBounds(bounds);
        renderTable();
        let msg = `미리보기: ${placed}건 표시`;
        if (failed.length) msg += ` · 위치 못 찾음 ${failed.length}건(주소 입력 후 다시 미리보기, 또는 📍로 직접 지정)`;
        banner(msg, failed.length ? 'warning' : 'success');
    }

    // ── 붙여넣기 ──
    function importTsv(text, mode) {
        const lines = text.split(/\r?\n/).filter((l) => l.trim());
        const parsed = [];
        for (const line of lines) {
            const c = line.split('\t');
            const no = (c[0] || '').trim();
            const name = (c[1] || '').trim();
            const manager = (c[2] || '').trim();
            const pctRaw = (c[3] || '').replace(/[%\s,]/g, '');
            const addr = (c[4] || '').trim();
            // 헤더 줄 스킵
            if (/공사명|담당자|공번/.test(line) && !/\d/.test(pctRaw)) {
                if (name === '공사명' || no === '공번') continue;
            }
            if (!name) continue;
            parsed.push({
                _id: uid(), no, name, manager,
                percent: pctRaw === '' ? 0 : (Number(pctRaw) || 0),
                addr, lat: null, lng: null, pinned: false,
            });
        }
        if (!parsed.length) { banner('불러올 행이 없습니다. 형식을 확인하세요.', 'warning'); return; }
        if (mode === 'append') {
            rows = rows.concat(parsed);
        } else {
            clearMarkers();
            rows = parsed;
        }
        renderTable();
        banner(`${parsed.length}건 불러왔습니다. ‘지도 미리보기’로 위치를 확인하세요.`, 'success');
        $('pasteArea').value = '';
        $('pasteBox').classList.add('d-none');
    }

    // ── 저장 ──
    async function save() {
        const payload = {
            month_label: $('monthLabel').value.trim(),
            sites: rows.filter((r) => String(r.name || '').trim()).map((r) => ({
                no: String(r.no || '').trim(),
                name: String(r.name || '').trim(),
                manager: String(r.manager || '').trim(),
                percent: Number(r.percent) || 0,
                addr: String(r.addr || '').trim(),
                lat: r.pinned ? r.lat : null,
                lng: r.pinned ? r.lng : null,
            })),
        };
        try {
            const res = await fetch('/api/progress-sites', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (res.status === 401) { banner('로그인이 필요합니다.', 'danger'); return; }
            if (res.status === 403) { banner('저장 권한이 없습니다(관리자 전용).', 'danger'); return; }
            const data = await res.json().catch(() => ({}));
            if (!res.ok) { banner('저장 실패: ' + (data.detail || res.status), 'danger'); return; }
            banner(`저장 완료(${(data.sites || []).length}건). 홈 화면을 새로고침하면 지도에 반영됩니다.`, 'success');
        } catch (_e) {
            banner('저장 중 네트워크 오류가 발생했습니다.', 'danger');
        }
    }

    // ── 초기 로딩 ──
    async function loadExisting() {
        try {
            const res = await fetch('/api/progress-sites');
            if (res.status === 401) { banner('로그인이 필요합니다. 홈에서 로그인 후 다시 들어오세요.', 'danger'); return; }
            if (!res.ok) { banner('데이터를 불러오지 못했습니다.', 'warning'); return; }
            const data = await res.json();
            $('monthLabel').value = data.month_label || '';
            rows = (Array.isArray(data.sites) ? data.sites : []).map((s) => ({
                _id: uid(),
                no: s.no || '',
                name: s.name || '',
                manager: s.manager || '',
                percent: s.percent != null ? s.percent : 0,
                addr: s.addr || '',
                lat: s.lat != null ? Number(s.lat) : null,
                lng: s.lng != null ? Number(s.lng) : null,
                pinned: (s.lat != null && s.lng != null),
            }));
            renderTable();
        } catch (_e) {
            banner('데이터 로딩 중 오류가 발생했습니다.', 'danger');
        }
    }

    async function showWhoami() {
        try {
            const res = await fetch('/api/auth/me');
            if (res.ok) {
                const me = await res.json();
                if (me.user_id) $('whoami').textContent = '· ' + me.user_id;
            }
        } catch (_e) { /* noop */ }
    }

    function init() {
        $('rowsBody').addEventListener('input', onBodyInput);
        $('rowsBody').addEventListener('click', onBodyClick);
        $('btnAddRow').addEventListener('click', () => {
            rows.push({ _id: uid(), no: '', name: '', manager: '', percent: 0, addr: '', lat: null, lng: null, pinned: false });
            renderTable();
        });
        $('btnPaste').addEventListener('click', () => $('pasteBox').classList.toggle('d-none'));
        $('btnPasteApply').addEventListener('click', () => {
            const mode = document.querySelector('input[name="pasteMode"]:checked').value;
            importTsv($('pasteArea').value, mode);
        });
        $('btnPreview').addEventListener('click', () => preview().catch(() => banner('미리보기 중 오류가 발생했습니다.', 'danger')));
        $('btnSave').addEventListener('click', save);

        showWhoami();
        loadExisting();
    }

    window.addEventListener('load', init);
})();
