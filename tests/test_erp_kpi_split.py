"""
대시보드 실적 분리(split) — ERP 응답 재포장 규칙 (2026-09-28).

split.construction 은 도넛의 분자, split.settlement 는 캡션의 정산 줄이다.
둘 다 "표의 합계 == 화면의 숫자"라, 행이 하나라도 새면 그 섹션만 통째로 버린다(None).
split 이 없으면(옛 ERP) None — 화면은 monthlyRevenue 로 대신 채우지 않는다(home.js).
"""
from app.api.erp import _normalize_monthly_kpi


def _payload(split=None):
    body = {
        "label": "9월",
        "amounts": {"monthlyRevenue": 293_816_000},
        "formatted": {"monthlyRevenue": "2.94억"},
        "updatedAt": "2026-09-28T03:00:00Z",
    }
    if split is not None:
        body["split"] = split
    return body


def _c_row(no="JG26-041", amount=32450, days=None, nights=None):
    return {
        "지중no": no,
        "공사명": "안양 평촌대로 지중화",
        "금액천원": amount,
        "일자": days if days is not None else [1, 2],
        "야간일자": nights if nights is not None else [2],
    }


def _s_row(no="JG26-018", kind="기성 2차", day=23, amount=30000):
    return {"지중no": no, "공사명": "군포 산본로", "구분": kind, "일": day, "금액천원": amount}


def test_split이_없으면_None():
    assert _normalize_monthly_kpi(_payload())["split"] is None


def test_split이_객체가_아니면_None():
    assert _normalize_monthly_kpi(_payload(split=[1, 2]))["split"] is None


def test_정상_응답은_두_섹션을_영문_키로_넘긴다():
    out = _normalize_monthly_kpi(_payload({
        "construction": {"rows": [_c_row()], "totalThousand": 32450},
        "settlement": {"rows": [_s_row(), _s_row(no="JG26-020", kind="준공", day=10, amount=-1182)],
                       "totalThousand": 28818},
    }))["split"]

    c = out["construction"]
    assert c["rows"][0] == {
        "jijungNo": "JG26-041", "name": "안양 평촌대로 지중화",
        "amountThousand": 32450, "days": [1, 2], "nightDays": [2], "dates": [], "nightDates": [],
        "managers": None,
    }
    assert c["totalThousand"] == 32450

    s = out["settlement"]
    assert s["rows"][0] == {
        "jijungNo": "JG26-018", "name": "군포 산본로", "kind": "기성 2차", "day": 23, "date": None, "amountThousand": 30000,
        "manager": None,
    }
    assert s["rows"][1]["amountThousand"] == -1182
    assert s["totalThousand"] == 28818


def test_construction_합계가_어긋나면_construction만_버리고_settlement는_유지():
    out = _normalize_monthly_kpi(_payload({
        "construction": {"rows": [_c_row(amount=100)], "totalThousand": 999},
        "settlement": {"rows": [_s_row(amount=500)], "totalThousand": 500},
    }))["split"]
    assert out["construction"] is None
    assert out["settlement"]["totalThousand"] == 500


def test_settlement_행이_하나라도_안_읽히면_settlement만_버린다():
    out = _normalize_monthly_kpi(_payload({
        "construction": {"rows": [_c_row(amount=100)], "totalThousand": 100},
        "settlement": {"rows": [_s_row(), "깨진 행"], "totalThousand": 30000},
    }))["split"]
    assert out["construction"]["totalThousand"] == 100
    assert out["settlement"] is None


def test_정산_일이_1에서_31_밖이면_None으로_둔다():
    out = _normalize_monthly_kpi(_payload({
        "construction": {"rows": [], "totalThousand": 0},
        "settlement": {"rows": [_s_row(day=45), _s_row(day="<b>")], "totalThousand": 60000},
    }))["split"]
    assert [r["day"] for r in out["settlement"]["rows"]] == [None, None]


def test_숫자가_문자열로_와도_정수로_강제한다():
    out = _normalize_monthly_kpi(_payload({
        "construction": {"rows": [_c_row(amount="1200")], "totalThousand": "1200"},
        "settlement": {"rows": [], "totalThousand": 0},
    }))["split"]
    assert out["construction"]["rows"][0]["amountThousand"] == 1200
    assert out["settlement"]["rows"] == []


def test_기존_breakdown_칸은_split과_무관하게_그대로():
    body = _payload({"construction": {"rows": [], "totalThousand": 0}, "settlement": {"rows": [], "totalThousand": 0}})
    body["breakdown"] = {"rows": [_c_row(amount=700)], "totalThousand": 700}
    out = _normalize_monthly_kpi(body)
    assert out["breakdown"]["totalThousand"] == 700
    assert out["amounts"]["monthlyRevenue"] == 293_816_000


# ── 금요일 기준 주차 (2026-10-23) ──
# split 의 기간은 달력 월이 아니라 그 주 금요일의 달이다(ERP 공무 화면과 같은 규칙). home.js 는 month 로 목표를 부른다.

def test_month_from_to를_넘기고_모양이_틀리면_None():
    ok = _normalize_monthly_kpi(_payload({
        "month": "2026-10", "from": "2026-09-28", "to": "2026-11-02",
        "construction": {"rows": [], "totalThousand": 0}, "settlement": {"rows": [], "totalThousand": 0},
    }))["split"]
    assert (ok["month"], ok["from"], ok["to"]) == ("2026-10", "2026-09-28", "2026-11-02")

    bad = _normalize_monthly_kpi(_payload({
        "month": "2026-13", "from": "<img>", "to": "2026/11/02",
        "construction": {"rows": [], "totalThousand": 0}, "settlement": {"rows": [], "totalThousand": 0},
    }))["split"]
    assert (bad["month"], bad["from"], bad["to"]) == (None, None, None)


def test_옛_ERP_split에는_month가_없어_None():
    out = _normalize_monthly_kpi(_payload({
        "construction": {"rows": [], "totalThousand": 0}, "settlement": {"rows": [], "totalThousand": 0},
    }))["split"]
    assert out["month"] is None


def test_달을_넘는_날짜는_전체_날짜로_넘기고_모양이_틀린_값은_버린다():
    row = _c_row(days=[31, 1], nights=[31])
    row["날짜"] = ["2026-08-31", "2026-09-01", "<script>"]
    row["야간날짜"] = ["2026-08-31"]
    s = _s_row(day=31)
    s["날짜"] = "2026-08-31"
    out = _normalize_monthly_kpi(_payload({
        "month": "2026-09", "from": "2026-08-31", "to": "2026-09-28",
        "construction": {"rows": [row], "totalThousand": 32450},
        "settlement": {"rows": [s], "totalThousand": 30000},
    }))["split"]
    c = out["construction"]["rows"][0]
    assert c["dates"] == ["2026-08-31", "2026-09-01"]
    assert c["nightDates"] == ["2026-08-31"]
    assert out["settlement"]["rows"][0]["date"] == "2026-08-31"


# ── 시공 담당별 (2026-10-29) ── 시공 담당은 ERP 공사이력.담당공무_id 한 곳에서 정한다.
# 대시보드는 그 나눔을 그대로 받아 담당자 칸에 넣는다(자체 배정표로 다시 나누지 않는다).

def _m(name, amount, dates=None, nights=None, mid=7):
    return {"담당공무_id": mid, "담당": name, "금액천원": amount,
            "날짜": dates if dates is not None else ["2026-10-02"], "야간날짜": nights if nights is not None else []}


def _split_with(rows):
    total = sum(r["금액천원"] for r in rows)
    return _normalize_monthly_kpi(_payload({
        "construction": {"rows": rows, "totalThousand": total},
        "settlement": {"rows": [], "totalThousand": 0},
    }))["split"]["construction"]


def test_담당별이_있으면_영문_키로_넘긴다():
    row = _c_row(amount=5002)
    row["담당별"] = [_m("이재규", 5000, ["2026-10-05"], ["2026-10-05"], mid=8), _m("김상훈", 2, ["2026-10-03", "2026-10-04"])]
    out = _split_with([row])
    assert out["rows"][0]["managers"] == [
        {"name": "이재규", "amountThousand": 5000, "dates": ["2026-10-05"], "nightDates": ["2026-10-05"]},
        {"name": "김상훈", "amountThousand": 2, "dates": ["2026-10-03", "2026-10-04"], "nightDates": []},
    ]


def test_미지정_담당은_빈_이름으로_남긴다():
    row = _c_row(amount=3000)
    row["담당별"] = [_m("", 3000, mid=None)]
    assert _split_with([row])["rows"][0]["managers"][0]["name"] == ""


def test_담당별이_없으면_None_옛_ERP():
    assert _split_with([_c_row()])["rows"][0]["managers"] is None


def test_담당별_합이_공사_금액과_다르면_그_행의_담당별을_버린다():
    # 담당자 칸의 합이 도넛과 어긋나느니, 그 행은 옛 규칙(목표 행·계획외)으로 나누는 게 낫다 — 섹션은 살린다
    row = _c_row(amount=5002)
    row["담당별"] = [_m("이재규", 5000)]
    out = _split_with([row])
    assert out["rows"][0]["managers"] is None
    assert out["totalThousand"] == 5002


# ── 정산 담당 (2026-10-29) ── 정산 담당은 ERP 수주.정산담당자_id 한 곳에서 정한다(공사 하나 = 한 사람).

def _settle(rows):
    return _normalize_monthly_kpi(_payload({
        "construction": {"rows": [], "totalThousand": 0},
        "settlement": {"rows": rows, "totalThousand": sum(r["금액천원"] for r in rows)},
    }))["split"]["settlement"]


def test_정산_담당이_있으면_manager로_넘긴다():
    row = _s_row()
    row["담당"] = "김도윤"
    assert _settle([row])["rows"][0]["manager"] == "김도윤"


def test_정산_미지정은_빈_이름으로_남긴다():
    row = _s_row()
    row["담당"] = ""
    assert _settle([row])["rows"][0]["manager"] == ""


def test_정산_담당_칸이_없으면_None_옛_ERP():
    assert _settle([_s_row()])["rows"][0]["manager"] is None
