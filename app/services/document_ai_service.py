"""문서 필드 AI 추천·이미지 추출 (Gemini, index/백엔드와 동일 API 키)."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.services.document_templates_service import field_ai_recommendable

logger = logging.getLogger(__name__)


class _ConstructionPlanJobModel(BaseModel):
    team: str = Field(
        default="",
        description='팀명. "공사1팀","공사2팀","공사3팀","기타"가 보이면 그대로, 없으면 빈 문자열.',
    )
    task: str = Field(
        description="**공사·작업 한 건**의 제목 한 줄(공사명·현장·구간 요약). 표의 물리적 행이 아니라 실제 공사 단위.",
    )
    work_code: str = Field(
        default="",
        description="작업코드. (SY26-005), <JY26-001>, 【코드】 등 불규칙 괄호 허용. 없거나 판독 불가면 빈 문자열.",
    )
    workers: str = Field(default="", description="해당 공사 작업자 이름.")
    details: str = Field(default="", description="작업내용 본문. 차량·장비 제외.")
    equipment: str = Field(default="", description="차량 및 장비.")
    shift_note: str = Field(default="", description="야간·주간, 날짜 범위 등 비고.")


class _ConstructionPlanRootModel(BaseModel):
    work_date_iso: str = Field(
        default="",
        description="표 상단 작업일자를 YYYY-MM-DD. 불명확하면 빈 문자열.",
    )
    jobs: List[_ConstructionPlanJobModel] = Field(
        default_factory=list,
        description="공사 단위별 객체. 한 팀 칸에 여러 공사가 있으면 jobs에 여러 항목.",
    )


class DocumentAIService:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-3-flash-preview"

    async def suggest_field_values(
        self,
        fields: List[Dict[str, Any]],
        context_text: Optional[str],
        template_instruction: Optional[str] = None,
    ) -> Dict[str, str]:
        to_suggest = [
            f
            for f in fields
            if isinstance(f, dict) and field_ai_recommendable(str(f.get("label", "")))
        ]
        if not to_suggest:
            return {}
        lines = []
        for f in to_suggest:
            lines.append(f"- id: {f.get('id')} / 라벨: {f.get('label', '')}")
        field_block = "\n".join(lines)
        ctx = (context_text or "").strip() or "(사용자가 추가 문맥을 제공하지 않았습니다. 일반적인 현장 문서 톤으로 짧게 제안하세요.)"
        doc_hint = ""
        if template_instruction and template_instruction.strip():
            doc_hint = f"[이 템플릿 전용 지시 — 아래만 추가로 따르세요]\n{template_instruction.strip()}\n\n"
        prompt = f"""당신은 건설 현장 문서 작성 보조입니다.
{doc_hint}아래 필드 중, 라벨에 (추천)이 포함된 항목만 JSON 객체로 값을 제안하세요.
날짜·금액·수량 등 반드시 정확해야 하는 값은 제안하지 말고 빈 문자열 "" 로 두세요.
키는 반드시 필드 id 문자열이어야 하고, 다른 키는 넣지 마세요.

[필드]
{field_block}

[참고 문맥]
{ctx}

응답은 JSON 객체만 출력하세요."""

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
            data = json.loads(response.text or "{}")
            if not isinstance(data, dict):
                return {}
            out: Dict[str, str] = {}
            allowed_ids = {str(f.get("id")) for f in to_suggest if f.get("id") is not None}
            for k, v in data.items():
                sk = str(k)
                if sk not in allowed_ids:
                    continue
                out[sk] = "" if v is None else str(v).strip()
            return out
        except Exception as e:
            logger.error("문서 필드 추천 실패: %s", e)
            return {}

    async def extract_field_values_from_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        fields: List[Dict[str, Any]],
        template_instruction: Optional[str] = None,
    ) -> Dict[str, str]:
        lines = []
        for f in fields:
            if not isinstance(f, dict):
                continue
            lines.append(f"- id: {f.get('id')} / 의미: {f.get('label', '')}")
        field_block = "\n".join(lines)
        doc_hint = ""
        if template_instruction and template_instruction.strip():
            doc_hint = f"[이 템플릿 전용 지시]\n{template_instruction.strip()}\n\n"
        prompt = f"""이미지에 보이는 문서에서 아래 필드에 해당하는 내용만 추출하세요.
확실하지 않으면 빈 문자열 "" 를 사용하세요.
키는 필드 id 와 정확히 일치하는 JSON 객체 하나만 출력하세요.

{doc_hint}[추출할 필드]
{field_block}
"""

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type or "image/jpeg"),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            data = json.loads(response.text or "{}")
            if not isinstance(data, dict):
                return {}
            allowed_ids = {str(f.get("id")) for f in fields if isinstance(f, dict) and f.get("id") is not None}
            out: Dict[str, str] = {}
            for k, v in data.items():
                sk = str(k)
                if sk not in allowed_ids:
                    continue
                out[sk] = "" if v is None else str(v).strip()
            return out
        except Exception as e:
            logger.error("문서 이미지 추출 실패: %s", e)
            return {}

    async def extract_table_rows_from_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        columns: List[Dict[str, str]],
        template_instruction: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        표 이미지에서 행 배열 추출. columns: [{"id", "header"}, ...]
        응답 JSON: {"rows": [ { col_id: str, ... }, ... ]}
        """
        if not columns:
            return []
        allowed = {c["id"] for c in columns}
        col_lines = [f'- id: "{c["id"]}" / 열 의미: {c["header"]}' for c in columns]
        col_block = "\n".join(col_lines)
        doc_hint = ""
        if template_instruction and template_instruction.strip():
            doc_hint = f"[이 템플릿 전용 지시]\n{template_instruction.strip()}\n\n"
        prompt = f"""이미지에 보이는 **표(자재 입고·출고·검수·재고 등)**에서 데이터 행만 읽으세요.

{doc_hint}[열 정의 — 각 행 객체의 키는 아래 id만 사용]
{col_block}

규칙:
- 표 **헤더(제목 행)**는 rows에 넣지 마세요. 숫자·품목이 나열된 **데이터 행만** 순서대로 넣으세요.
- 이미지에 보이는 데이터 행을 **빠짐없이** 추출하세요. 비어 있는 셀은 빈 문자열 "" 로 두세요.
- 병합된 셀은 보이는 텍스트를 해당 내용이 적용되는 첫 데이터 행에 반영하세요.
- 확실히 읽을 수 없는 칸만 "" 로 두고, 추측으로 숫자를 바꾸지 마세요.
- 한 행에 없는 열 id는 생략하거나 "" 로 두세요.
- 최대 200행까지. 그 이상이면 앞쪽 200행만.

응답은 반드시 JSON 하나만: {{"rows": [ 객체, ... ]}} 형태. 다른 키는 넣지 마세요."""

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type or "image/jpeg"),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            data = json.loads(response.text or "{}")
            if not isinstance(data, dict):
                return []
            raw_rows = data.get("rows")
            if not isinstance(raw_rows, list):
                return []
            out: List[Dict[str, str]] = []
            for item in raw_rows:
                if not isinstance(item, dict):
                    continue
                row: Dict[str, str] = {}
                for k in allowed:
                    if k not in item:
                        row[k] = ""
                        continue
                    v = item[k]
                    row[k] = "" if v is None else str(v).strip()
                out.append(row)
            return out
        except Exception as e:
            logger.error("표 이미지 추출 실패: %s", e)
            return []

    async def extract_construction_schedule_plan(
        self,
        image_bytes: bytes,
        mime_type: str,
        column_ids: List[str],
        template_instruction: Optional[str] = None,
    ) -> Tuple[List[Dict[str, str]], str]:
        """
        공사 일정 계획서 전용: 표의 '팀 행'이 아니라 **공사·작업 건** 단위로 jobs를 채운다.
        반환: (검토용 행 dict 목록, 헤더 작업일자 YYYY-MM-DD 또는 빈 문자열)
        """
        doc_hint = ""
        if template_instruction and template_instruction.strip():
            doc_hint = f"[템플릿 메모 — 참고]\n{template_instruction.strip()}\n\n"
        prompt = f"""당신은 한국 전력·건설 현장의 **공사일정계획서(손글씨/인쇄 양식)**를 읽는 비서입니다.

{doc_hint}[핵심 규칙]
1) 출력의 `jobs` 배열은 **실제 공사·작업이 몇 건이든 그만큼** 객체를 넣습니다. 인쇄된 표의 데이터 행 수와 같을 필요가 **없습니다**.
2) **한 팀(공사1팀 등) 칸 안에** 서로 다른 공사가 2~3건 적혀 있으면(불릿·줄바꿈·번호로 구분) → **각각 별도 job**으로 나눕니다. 각 job의 `team`에는 같은 팀명을 반복해도 됩니다.
3) 팀이 다르지만 한 건의 연속 작업처럼 보이면 사람이 상황판에 나눌 기준에 맞게 1건 또는 여러 건으로 판단합니다.
4) `task`는 그 공사 한 건을 식별할 수 있는 **짧은 한 줄 제목**입니다.
5) `work_code`: 공사명 옆·근처에 보이는 코드만. `(SY26-005)`, `<JY26-001)`, `JY26-001` 등 **불완전한 괄호**도 그대로 옮기되, 전혀 없거나 글자가 확실하지 않으면 빈 문자열.
6) `details`에는 작업내용·구간·재질 등(차량/장비 제외). `equipment`에는 차량 및 장비 열 내용.
7) `shift_note`: 야간·주간, "4/15~4/16(야간)" 같은 기간 표기.
8) 표 상단 **작업일자**를 읽어 `work_date_iso`에 **YYYY-MM-DD**만 넣습니다. 한글 "2026년 4월 16일"도 변환합니다. 확실하지 않으면 빈 문자열.
9) 빈 칸·의미 없는 행은 job으로 넣지 않습니다. `기타` 행에 실질 일정이 있으면 1건 이상으로 넣습니다.

응답은 스키마에 맞는 JSON 한 덩어리만."""

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type or "image/jpeg"),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_ConstructionPlanRootModel,
                    temperature=0.05,
                ),
            )
            raw_text = (response.text or "").strip() or "{}"
            parsed = _ConstructionPlanRootModel.model_validate_json(raw_text)
        except Exception as e:
            logger.error("공사일정계획서 추출 실패: %s", e)
            return [], ""

        allowed = [x for x in column_ids if x.strip()]
        if not allowed:
            allowed = ["team", "task", "work_code", "workers", "details", "equipment", "shift_note"]

        rows: List[Dict[str, str]] = []
        for job in parsed.jobs:
            base = {
                "team": (job.team or "").strip(),
                "task": (job.task or "").strip(),
                "work_code": (job.work_code or "").strip(),
                "workers": (job.workers or "").strip(),
                "details": (job.details or "").strip(),
                "equipment": (job.equipment or "").strip(),
                "shift_note": (job.shift_note or "").strip(),
            }
            if not any(base.values()):
                continue
            if not base["task"]:
                continue
            row = {k: base.get(k, "") for k in allowed}
            rows.append(row)

        return rows, (parsed.work_date_iso or "").strip()
