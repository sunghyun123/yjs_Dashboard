import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.auth import require_session
from app.core.config import settings
from app.services.document_ai_service import DocumentAIService
from app.services.document_templates_service import (
    build_xlsx_table_bytes,
    field_ai_recommendable,
    get_template_by_id,
    load_templates_manifest,
    normalize_table_columns,
    render_filled_document,
    required_gate_field_ids,
    resolve_template_file,
    template_ai_extract_instruction,
    template_ai_suggest_instruction,
    validate_template_required_gates,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["Documents"])

_doc_ai: Optional[DocumentAIService] = None


def _templates_base() -> Path:
    return Path(settings.DOCUMENT_TEMPLATES_DIR).resolve()


def _ai() -> DocumentAIService:
    global _doc_ai
    if _doc_ai is None:
        _doc_ai = DocumentAIService(api_key=settings.GEMINI_API_KEY)
    return _doc_ai


def _ascii_download_basename(template_id: str) -> str:
    """HTTP Content-Disposition filename= 은 latin-1만 안전. 한글 id는 제거( str.isalnum() 은 한글도 True )."""
    raw = "".join(c for c in str(template_id) if ord(c) < 128 and (c.isalnum() or c in ("-", "_")))
    raw = raw.strip("-_") or "document"
    return raw[:120] if len(raw) > 120 else raw


def _content_disposition_attachment(template_id: str, ext: str, title: Optional[str] = None) -> str:
    base = _ascii_download_basename(template_id)
    primary = f"{base}{ext}"
    line = f'attachment; filename="{primary}"'
    disp_title = (title or "").strip()
    if disp_title:
        safe_star = quote(f"{disp_title}{ext}", safe="")
        line += f"; filename*=UTF-8''{safe_star}"
    return line


def _sanitize_field_options(raw: Any) -> Optional[List[Dict[str, str]]]:
    if not isinstance(raw, list):
        return None
    out: List[Dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        v = item.get("value")
        if v is None:
            continue
        lab = item.get("label")
        out.append({"value": str(v), "label": str(lab) if lab is not None else str(v)})
    return out or None


def _public_template_view(t: Dict[str, Any]) -> Dict[str, Any]:
    fields_out: List[Dict[str, Any]] = []
    for f in t.get("fields") or []:
        if not isinstance(f, dict):
            continue
        fid = f.get("id")
        if fid is None:
            continue
        label = str(f.get("label", ""))
        opts = _sanitize_field_options(f.get("options"))
        row: Dict[str, Any] = {
            "id": str(fid),
            "label": label,
            "ai_recommend": field_ai_recommendable(label),
            "cell": f.get("cell"),
            "placeholder": f.get("placeholder"),
        }
        if opts:
            row["options"] = opts
        fields_out.append(row)
    rg = t.get("required_gate")
    required_gate_out: List[str] = []
    if isinstance(rg, list):
        required_gate_out = [str(x).strip() for x in rg if str(x).strip()]

    table_cols_raw = t.get("table_columns")
    table_columns_out: List[Dict[str, str]] = []
    if isinstance(table_cols_raw, list):
        for c in table_cols_raw:
            if not isinstance(c, dict) or c.get("id") is None:
                continue
            cid = str(c.get("id", "")).strip()
            if not cid:
                continue
            table_columns_out.append(
                {
                    "id": cid,
                    "header": str(c.get("header", cid)).strip() or cid,
                }
            )

    em = str(t.get("extract_mode") or "").strip().lower()
    extract_mode_out = "table" if em == "table" else "fields"
    generate_enabled = bool(t.get("generate_enabled", True))
    extract_enabled = bool(t.get("extract_enabled", True))

    out: Dict[str, Any] = {
        "id": str(t.get("id", "")),
        "title": str(t.get("title", "")),
        "kind": str(t.get("kind", "")),
        "required_gate": required_gate_out,
        "generate_enabled": generate_enabled,
        "extract_enabled": extract_enabled,
        "extract_mode": extract_mode_out,
        "fields": fields_out,
    }
    if extract_mode_out == "table":
        out["table_columns"] = table_columns_out
    return out


@router.get("/templates", summary="문서 템플릿 목록(필드 메타)")
def list_document_templates(_session=Depends(require_session)):
    base = _templates_base()
    try:
        items = load_templates_manifest(base)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"templates": [_public_template_view(t) for t in items if t.get("id")]}


class DocumentSuggestRequest(BaseModel):
    template_id: str = Field(..., description="templates.json 의 id")
    context_text: Optional[str] = Field(default=None, description="참고할 문맥(선택)")
    values: Dict[str, Any] = Field(
        default_factory=dict,
        description="현재 폼 값(필수 게이트 검증 및 AI 문맥 보강)",
    )


@router.post("/suggest", summary="AI 필드 값 추천((추천) 라벨만)")
async def suggest_document_values(body: DocumentSuggestRequest, _session=Depends(require_session)):
    base = _templates_base()
    template = get_template_by_id(base, body.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    if not bool(template.get("generate_enabled", True)):
        raise HTTPException(status_code=400, detail="문서 생성이 비활성화된 템플릿입니다.")
    raw_values = {str(k): ("" if v is None else str(v)) for k, v in (body.values or {}).items()}
    try:
        validate_template_required_gates(template, raw_values)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    gate_ids = required_gate_field_ids(template)
    ctx = (body.context_text or "").strip()
    if gate_ids:
        lines = [f"- {gk}: {raw_values.get(gk, '').strip()}" for gk in gate_ids]
        prefix = "[필수 식별 정보 — 아래만 작업 범위로 간주]\n" + "\n".join(lines)
        ctx = f"{prefix}\n\n{ctx}" if ctx else prefix
    ctx_out: Optional[str] = ctx if ctx else None
    fields = [f for f in (template.get("fields") or []) if isinstance(f, dict)]
    suggested = await _ai().suggest_field_values(
        fields,
        ctx_out,
        template_instruction=template_ai_suggest_instruction(template),
    )
    return {"values": suggested}


class DocumentFillRequest(BaseModel):
    template_id: str
    values: Dict[str, Any] = Field(default_factory=dict)


@router.post("/fill", summary="템플릿에 값을 넣어 파일 생성")
def fill_document(body: DocumentFillRequest, _session=Depends(require_session)):
    base = _templates_base()
    template = get_template_by_id(base, body.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    if not bool(template.get("generate_enabled", True)):
        raise HTTPException(status_code=400, detail="문서 생성이 비활성화된 템플릿입니다.")
    try:
        raw_values = {str(k): ("" if v is None else str(v)) for k, v in (body.values or {}).items()}
        validate_template_required_gates(template, raw_values)
        blob, mime, ext = render_filled_document(base, body.template_id, raw_values)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        logger.exception("문서 생성 실패")
        raise HTTPException(status_code=500, detail="문서 생성 중 오류가 발생했습니다.") from e

    template_meta = get_template_by_id(base, body.template_id) or {}
    title = template_meta.get("title")
    title_str = str(title).strip() if title is not None else ""
    return Response(
        content=blob,
        media_type=mime,
        headers={"Content-Disposition": _content_disposition_attachment(body.template_id, ext, title_str or None)},
    )


@router.post("/extract", summary="이미지에서 템플릿 필드 또는 표 행 추출")
async def extract_document_fields(
    template_id: str = Form(...),
    file: UploadFile = File(...),
    _session=Depends(require_session),
):
    base = _templates_base()
    template = get_template_by_id(base, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    if not bool(template.get("extract_enabled", True)):
        raise HTTPException(status_code=400, detail="문서 추출이 비활성화된 템플릿입니다.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="이미지 파일이 비어 있습니다.")
    mime = file.content_type or "image/jpeg"

    extract_mode = str(template.get("extract_mode") or "").strip().lower()
    if extract_mode == "table":
        cols = normalize_table_columns(template)
        if not cols:
            raise HTTPException(
                status_code=400,
                detail="표 추출 템플릿에 table_columns 정의가 필요합니다.",
            )
        if str(template_id).strip() == "construction_schedule_xlsx":
            col_ids = [str(c.get("id", "")).strip() for c in cols if c.get("id")]
            rows, header_iso = await _ai().extract_construction_schedule_plan(
                data,
                mime,
                col_ids,
                template_instruction=template_ai_extract_instruction(template),
            )
            values_out: Dict[str, str] = {}
            if header_iso:
                values_out["constuction_time"] = header_iso
            return {"extract_mode": "table", "rows": rows, "values": values_out}
        rows = await _ai().extract_table_rows_from_image(
            data,
            mime,
            cols,
            template_instruction=template_ai_extract_instruction(template),
        )
        return {"extract_mode": "table", "rows": rows, "values": {}}

    try:
        resolve_template_file(base, template)
    except Exception:
        raise HTTPException(status_code=400, detail="템플릿 파일이 유효하지 않습니다.") from None

    fields = [f for f in (template.get("fields") or []) if isinstance(f, dict)]
    extracted = await _ai().extract_field_values_from_image(
        data,
        mime,
        fields,
        template_instruction=template_ai_extract_instruction(template),
    )
    return {"extract_mode": "fields", "values": extracted}


class TableExportRequest(BaseModel):
    template_id: str
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    values: Dict[str, Any] = Field(default_factory=dict)


@router.post("/export-table", summary="추출된 표 행을 엑셀로보내기")
def export_table_xlsx(body: TableExportRequest, _session=Depends(require_session)):
    base = _templates_base()
    template = get_template_by_id(base, body.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    if not bool(template.get("extract_enabled", True)):
        raise HTTPException(status_code=400, detail="문서 추출이 비활성화된 템플릿입니다.")
    if str(template.get("extract_mode") or "").strip().lower() != "table":
        raise HTTPException(status_code=400, detail="표 추출 전용 템플릿이 아닙니다.")
    try:
        template_path = resolve_template_file(base, template)
        raw_values = {str(k): ("" if v is None else str(v)) for k, v in (body.values or {}).items()}
        blob = build_xlsx_table_bytes(template_path, template, list(body.rows or []), raw_values)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        logger.exception("표 엑셀 생성 실패")
        raise HTTPException(status_code=500, detail="엑셀 생성 중 오류가 발생했습니다.") from e

    title = template.get("title")
    title_str = str(title).strip() if title is not None else ""
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": _content_disposition_attachment(
                body.template_id, ".xlsx", title_str or None
            )
        },
    )
