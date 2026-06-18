(function () {
    // ═══════════════════════════════════════════════════════════════════════
    //  연동 키 (사용자 발급 후 입력) ─ 이 두 값만 채우면 지도/날씨가 동작합니다.
    // ───────────────────────────────────────────────────────────────────────
    //  카카오맵 JS 키는 서버 .env(KAKAO_MAP_JS_KEY)에 두고 `/api/public-config`로 받아온다.
    //    (도메인 제한이 걸린 공개 키이지만 코드/깃에 하드코딩하지 않기 위함)
    //  WEATHER_API_BASE: 날씨는 CORS/키 보호를 위해 백엔드 프록시(`/api/weather/current`) 경유.
    //    백엔드 엔드포인트가 준비되면 자동으로 실데이터가 표시됩니다.
    const WEATHER_API_BASE = '/api/weather/current';
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
    const JUN_TOTAL_PLAN_AMT    = 429250; // 천원 — 계획 목표금액
    // ─────────────────────────────────────────────────────────────────────────

    // 담당자별 핀 색상/약칭 (메모리 project-home-renewal 확정값)
    const MANAGER_STYLE = {
        '김무선': { color: '#2f6fed', short: '무선' },
        '김상훈': { color: '#e8590c', short: '상훈' },
        '이재규': { color: '#2f9e44', short: '이재' },
        '김단후': { color: '#ae3ec9', short: '단후' },
    };
    const DEFAULT_MANAGER_STYLE = { color: '#64748b', short: '담당' };

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
                `<br><span style="font-size:0.74rem;color:#7a8fa3;font-weight:500;white-space:nowrap;">(계획 ${JUN_PLAN_ACTUAL_AMT.toLocaleString('ko-KR')} + 계획외 ${JUN_EXTRA_ACTUAL_AMT.toLocaleString('ko-KR')}천원)</span>` +
                `<br><span style="white-space:nowrap;">목표 <b>${JUN_TOTAL_PLAN_AMT.toLocaleString('ko-KR')}천원</b></span>` +
                `<br><span style="font-size:0.71rem;color:#aab8c6;white-space:nowrap;">최신화 ${JUN_DATA_UPDATED}</span>`;
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
        renderTotalProgressChartHome();
        renderWeatherPlaceholder();
        initMapHome();
        await Promise.all([loadWorkerStatusHome(), loadFrequentSitesHome(), loadWeatherHome()]);
        setInterval(() => {
            updateNowLabel();
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
