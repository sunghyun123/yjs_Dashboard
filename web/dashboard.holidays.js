(function (global) {
    const OFFICIAL_HOLIDAYS_BY_YEAR = Object.freeze({
        // 2026년 월력요항 + 2026년 시행 노동절·제헌절 공휴일 재지정 반영
        2026: Object.freeze({
            '2026-01-01': '신정',
            '2026-02-16': '설날 연휴',
            '2026-02-17': '설날',
            '2026-02-18': '설날 연휴',
            '2026-03-01': '삼일절',
            '2026-03-02': '대체공휴일',
            '2026-05-01': '노동절',
            '2026-05-05': '어린이날',
            '2026-05-24': '부처님오신날',
            '2026-05-25': '대체공휴일',
            '2026-06-03': '전국동시지방선거일',
            '2026-06-06': '현충일',
            '2026-07-17': '제헌절',
            '2026-08-15': '광복절',
            '2026-08-17': '대체공휴일',
            '2026-09-24': '추석 연휴',
            '2026-09-25': '추석',
            '2026-09-26': '추석 연휴',
            '2026-10-03': '개천절',
            '2026-10-05': '대체공휴일',
            '2026-10-09': '한글날',
            '2026-12-25': '성탄절',
        }),
        // 2027년 우주항공청 월력요항 반영
        2027: Object.freeze({
            '2027-01-01': '신정',
            '2027-02-06': '설날 연휴',
            '2027-02-07': '설날',
            '2027-02-08': '설날 연휴',
            '2027-02-09': '대체공휴일',
            '2027-03-01': '삼일절',
            '2027-05-01': '노동절',
            '2027-05-03': '대체공휴일',
            '2027-05-05': '어린이날',
            '2027-05-13': '부처님오신날',
            '2027-06-06': '현충일',
            '2027-07-17': '제헌절',
            '2027-07-19': '대체공휴일',
            '2027-08-15': '광복절',
            '2027-08-16': '대체공휴일',
            '2027-09-14': '추석 연휴',
            '2027-09-15': '추석',
            '2027-09-16': '추석 연휴',
            '2027-10-03': '개천절',
            '2027-10-04': '대체공휴일',
            '2027-10-09': '한글날',
            '2027-10-11': '대체공휴일',
            '2027-12-25': '성탄절',
            '2027-12-27': '대체공휴일',
        }),
    });

    const computedYearCache = new Map();
    let lunarFormatter;

    function validDateKey(value) {
        const raw = String(value || '').trim();
        const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
        if (!match) return null;
        const year = Number(match[1]);
        const month = Number(match[2]);
        const day = Number(match[3]);
        const date = new Date(Date.UTC(year, month - 1, day));
        if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
        return { key: raw, year, month, day };
    }

    function dateKeyFromUtc(date) {
        const year = date.getUTCFullYear();
        const month = String(date.getUTCMonth() + 1).padStart(2, '0');
        const day = String(date.getUTCDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    function shiftDateKey(dateKey, offset) {
        const parsed = validDateKey(dateKey);
        if (!parsed) return '';
        const date = new Date(Date.UTC(parsed.year, parsed.month - 1, parsed.day + offset));
        return dateKeyFromUtc(date);
    }

    function weekDay(dateKey) {
        const parsed = validDateKey(dateKey);
        if (!parsed) return -1;
        return new Date(Date.UTC(parsed.year, parsed.month - 1, parsed.day)).getUTCDay();
    }

    function addHoliday(map, dateKey, name) {
        if (!dateKey || !name) return;
        const names = map.get(dateKey) || [];
        if (!names.includes(name)) names.push(name);
        map.set(dateKey, names);
    }

    function lunarMonthDay(dateKey) {
        try {
            if (!lunarFormatter) {
                lunarFormatter = new Intl.DateTimeFormat('ko-KR-u-ca-chinese', {
                    month: 'numeric',
                    day: 'numeric',
                    timeZone: 'Asia/Seoul',
                });
            }
            const parsed = validDateKey(dateKey);
            if (!parsed) return null;
            const noonInKorea = new Date(Date.UTC(parsed.year, parsed.month - 1, parsed.day, 3));
            const parts = lunarFormatter.formatToParts(noonInKorea);
            const month = parts.find((part) => part.type === 'month')?.value || '';
            const day = parts.find((part) => part.type === 'day')?.value || '';
            if (!/^\d+$/.test(month) || !/^\d+$/.test(day)) return null;
            return { month: Number(month), day: Number(day) };
        } catch (_error) {
            return null;
        }
    }

    function findLunarDate(year, targetMonth, targetDay) {
        const start = new Date(Date.UTC(year, 0, 1));
        const end = new Date(Date.UTC(year, 11, 31));
        for (let cursor = new Date(start); cursor <= end; cursor.setUTCDate(cursor.getUTCDate() + 1)) {
            const key = dateKeyFromUtc(cursor);
            const lunar = lunarMonthDay(key);
            if (lunar?.month === targetMonth && lunar?.day === targetDay) return key;
        }
        return '';
    }

    function nextNonHoliday(map, dateKey) {
        let candidate = shiftDateKey(dateKey, 1);
        while (candidate && (map.has(candidate) || weekDay(candidate) === 0)) {
            candidate = shiftDateKey(candidate, 1);
        }
        return candidate;
    }

    function buildComputedYear(year) {
        const map = new Map();
        const fixed = [
            ['01-01', '신정', false],
            ['03-01', '삼일절', true],
            ['05-05', '어린이날', true],
            ['06-06', '현충일', false],
            ['08-15', '광복절', true],
            ['10-03', '개천절', true],
            ['10-09', '한글날', true],
            ['12-25', '성탄절', true],
        ];
        if (year >= 2026) {
            fixed.push(['05-01', '노동절', true], ['07-17', '제헌절', true]);
        }
        fixed.forEach(([monthDay, name]) => addHoliday(map, `${year}-${monthDay}`, name));

        const lunarNewYear = findLunarDate(year, 1, 1);
        const buddhaBirthday = findLunarDate(year, 4, 8);
        const chuseok = findLunarDate(year, 8, 15);
        const lunarGroups = [];
        if (lunarNewYear) {
            const days = [shiftDateKey(lunarNewYear, -1), lunarNewYear, shiftDateKey(lunarNewYear, 1)];
            addHoliday(map, days[0], '설날 연휴');
            addHoliday(map, days[1], '설날');
            addHoliday(map, days[2], '설날 연휴');
            lunarGroups.push({ days, name: '설날 대체공휴일' });
        }
        if (buddhaBirthday) addHoliday(map, buddhaBirthday, '부처님오신날');
        if (chuseok) {
            const days = [shiftDateKey(chuseok, -1), chuseok, shiftDateKey(chuseok, 1)];
            addHoliday(map, days[0], '추석 연휴');
            addHoliday(map, days[1], '추석');
            addHoliday(map, days[2], '추석 연휴');
            lunarGroups.push({ days, name: '추석 대체공휴일' });
        }

        const substitutionEvents = [];
        lunarGroups.forEach((group) => {
            const needsSubstitute = group.days.some((key) => weekDay(key) === 0 || (map.get(key) || []).length > 1);
            if (needsSubstitute) substitutionEvents.push({ anchor: group.days[group.days.length - 1], name: group.name });
        });

        const eligibleSingleDates = fixed
            .filter(([, , substituteEligible]) => substituteEligible)
            .map(([monthDay]) => `${year}-${monthDay}`);
        if (buddhaBirthday) eligibleSingleDates.push(buddhaBirthday);
        [...new Set(eligibleSingleDates)].forEach((dateKey) => {
            const names = map.get(dateKey) || [];
            if (weekDay(dateKey) === 0 || weekDay(dateKey) === 6 || names.length > 1) {
                substitutionEvents.push({ anchor: dateKey, name: '대체공휴일' });
            }
        });

        substitutionEvents.sort((a, b) => a.anchor.localeCompare(b.anchor));
        substitutionEvents.forEach((event) => addHoliday(map, nextNonHoliday(map, event.anchor), event.name));
        return map;
    }

    function holidaysForYear(year) {
        if (!computedYearCache.has(year)) {
            const official = OFFICIAL_HOLIDAYS_BY_YEAR[year];
            const holidays = official
                ? new Map(Object.entries(official).map(([key, name]) => [key, [name]]))
                : buildComputedYear(year);
            computedYearCache.set(year, holidays);
        }
        return computedYearCache.get(year);
    }

    function get(dateKey) {
        const parsed = validDateKey(dateKey);
        if (!parsed) return null;
        const names = holidaysForYear(parsed.year).get(parsed.key);
        if (!names?.length) return null;
        return Object.freeze({ date: parsed.key, name: names.join(' · '), names: Object.freeze([...names]) });
    }

    global.DashboardHolidays = Object.freeze({ get, holidaysForYear });
})(window);
