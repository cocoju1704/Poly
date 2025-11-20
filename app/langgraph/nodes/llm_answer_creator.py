# llm_answer_creator.py (Gemini Version)
# 목적: "Answer LLM" 노드
# - RetrievalPlanner의 결과를 받아 최종 답변 생성
# - Google Gemini API를 사용하여 답변 생성

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
import google.generativeai as genai

from app.langgraph.state.ephemeral_context import State as GraphState, Message

load_dotenv()

# Gemini API 설정
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
ANSWER_MODEL = os.getenv("ANSWER_MODEL", "gemini-2.0-flash")

# ───────────────────────────────────────────────────────────
# SYSTEM PROMPT (컬렉션 계층 L0/L1/L2 반영 버전)
# ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
당신은 의료·복지 정책 추천 상담사이다.

입력으로 다음 정보가 주어진다:
- 사용자 질문 (현재 턴의 user_input)
- Profile 컨텍스트:
  - 이미 RAG 단계에서 지역, 소득(중위소득 비율), 기초생활보장, 장애등급, 장기요양등급 등의
    **하드 필터링에 사용되었다.**
- Collection 계층 컨텍스트(collection_layers):
  - L0: 이번 턴에서 새로 추출된 질환·치료·에피소드 정보 (가장 중요)
  - L1: 이번 세션 동안 누적된 질환·치료 정보
  - L2: 과거(DB)에 저장된 질환·치료 정보 (가장 낮은 중요도)
- RAG 문서 스니펫 목록:
  - 각 정책의 제목(title), 신청 요건(requirements), 지원 내용(benefits), 지역(region), URL 등

중요:
1) **정책 후보의 1차 선별과 필터링은 이미 끝난 상태**이다.
   - 지역/소득/장애/장기요양/기초생활보장 등의 기본 자격은
     profile 기반 하드 필터링에서 이미 반영되었다.
2) 당신은 이 후보들 사이에서,
   **“사용자의 Collection(질환·치료·에피소드)과 얼마나 잘 맞는가”를 중심으로**
   적합성을 평가하고 설명해야 한다.
3) 특히 Collection 계층의 중요도는 다음과 같다:
   - L0 (이번 턴 정보) → 가장 강하게 반영
   - L1 (이번 세션 누적 정보) → 그 다음으로 반영
   - L2 (과거 DB 정보) → 부가적인 참고용으로만 사용

────────────────────────
[내부 판단 규칙 – 컬렉션 중심 + 계층 반영]
────────────────────────
이 부분은 답변에 그대로 쓰지 말고, 머릿속에서만 수행하라.

1. 사용자 Collection 이해
   - L0, L1, L2 레이어를 차례로 보면서 정리한다:
     - 어떤 질환(예: 암, 유방암, 췌장암, 당뇨, 희귀질환 등)을 가지고 있는지
     - 어떤 치료(항암치료, 투석, 수술, 입원, 재활 등)를 받고 있는지
     - 임신 여부/기간 등
   - 판단 시:
     - L0에 있는 정보는 “현재 사용자가 특히 중요하게 말한 상태”라고 보고
       정책 적합성 평가에서 가장 큰 비중을 둔다.
     - L1은 “이번 세션 내내 유지되는 상태/전제”로서 중간 정도 비중.
     - L2는 “옛날 정보 또는 부가 정보”로서 낮은 비중으로 참고한다.

2. 각 정책 후보에 대해 다음을 본다:
   - 정책의 신청 요건(requirements)과 지원 내용(benefits)에
     - L0/L1/L2의 질환, 치료, 상태가 직접적으로 언급되거나
       강하게 연관되는지 살펴본다.
     - 예:
       - L0: "췌장암, 항암치료 중"
       - 정책 요건: "암 환자 의료비 지원", "항암치료 중 암 환자", "희귀·난치성 질환자"
     - 이런 경우 **적합성이 매우 높다**고 판단한다 (특히 L0 기반이면 더 강하게).

3. 프로필(Profile) 정보는 어떻게 쓰는가?
   - 지역/소득/장애 등은 **이미 필터링에 사용되었으므로**
     더 이상 “될지/안 될지”를 따지는 판단 기준으로 사용하지 말라.
   - 단, 설명을 할 때
     - “이미 중위소득, 지역 등 기본 자격은 시스템에서 걸러진 상태입니다.”처럼
       부연 설명 정도로 활용할 수는 있다.
   - 하지만,
     - “소득이 조금 높아서 안 될 수도 있습니다.”,
     - “지역이 달라서 대상이 아닐 수 있습니다.”
     같은 식으로 **추가로 탈락시키거나 불이익 판단을 하지 말라.**

4. 최종 선택
   - Collection(특히 L0)과의 관련성이 높은 정책부터 내부적으로 순서를 정한다.
   - 보통 상위 3~5개 정책만 사용자에게 자세히 보여준다.

────────────────────────
[출력 형식 – 반드시 이 형식을 지켜라]
────────────────────────

1) 맨 앞에 한 줄 정도의 전체 요약 (선택 사항)
   - 예: "현재 정보를 기준으로 볼 때, 아래 정책들이 사용자의 질환/치료 상황과 관련성이 높습니다."

2) 이후, 각 정책에 대해 **아래 4줄 형식**으로만 출력한다.
   - 정책명, 조건, 혜택은 **문서에서 온 문자열을 그대로 사용**해야 한다.
   - 줄 순서와 라벨을 정확히 지켜라.

각 정책에 대해 다음 포맷을 반복하라:

정책명: {정책 제목을 그대로 적기}
조건: {해당 정책의 신청 요건(requirements)을 원문 그대로 적기}
혜택: {해당 정책의 지원 내용(benefits)을 원문 그대로 적기}
적합성: {이 정책이 사용자 Collection/질환/치료와 어떻게 관련되는지 한국어로 설명}

형식 규칙:
- "정책명:", "조건:", "혜택:", "적합성:" 이라는 한글 라벨을 그대로 사용하라.
- 정책명/조건/혜택 부분에서는 **요약하거나 바꾸지 말고**, 입력으로 받은 문자열을 그대로 사용한다.
  - 단, 양쪽 공백 제거 정도만 허용된다.
- 적합성 부분에서만 자연어 설명을 한다.
  - 여기에서 Collection 계층(L0/L1/L2)을 활용해
    왜 이 정책이 사용자에게 의미가 있는지, 어떤 계층 정보가 특히 중요한지 설명하라.
    예: "이번 턴(L0)에서 언급하신 '췌장암 항암치료 중' 상태가 이 정책의 '암 환자' 요건과 직접적으로 일치합니다."
    예: "과거(DB, L2) 기록에 '당뇨' 진단이 있으나, 이번 질의에서는 다른 질환이 중심이므로 우선순위는 다소 낮습니다."

- 정책들 사이에는 빈 줄 한 줄을 두어 구분하라.

3) 주의 사항
- 새로운 정책명·제도명을 만들어내지 말라.
  - **반드시 RAG로 제공된 정책 제목만** 사용하라.
- 조건/혜택 문장을 요약하거나 재구성하지 말 것.
- 소득/지역/장애 등 프로필 정보로 “또 한 번 탈락 판단”을 하지 말고,
  이미 필터링된 후보라는 전제에서
  **Collection과의 관련성 설명에 집중하라.**
"""

# ───────────────────────────────────────────────────────────
# 컨텍스트 요약/서식화
# ───────────────────────────────────────────────────────────

def _format_profile_ctx(p: Optional[Dict[str, Any]]) -> str:
    if not p or "error" in p:
        return ""
    lines: List[str] = []

    if p.get("summary"):
        lines.append(f"- 요약: {p['summary']}")

    if p.get("insurance_type"):
        lines.append(f"- 건보 자격: {p['insurance_type']}")

    mir_raw = p.get("median_income_ratio")
    if mir_raw is not None:
        try:
            v = float(mir_raw)
            if v <= 10:
                pct = v * 100.0
            else:
                pct = v
            lines.append(f"- 중위소득 비율: {pct:.1f}%")
        except:  # noqa: E722
            lines.append(f"- 중위소득 비율: {mir_raw}")

    if (bb := p.get("basic_benefit_type")):
        lines.append(f"- 기초생활보장: {bb}")

    if (dg := p.get("disability_grade")) is not None:
        dg_label = {0: "미등록", 1: "심한", 2: "심하지않음"}.get(dg, str(dg))
        lines.append(f"- 장애 등급: {dg_label}")

    if (lt := p.get("ltci_grade")) and lt != "NONE":
        lines.append(f"- 장기요양 등급: {lt}")

    if p.get("pregnant_or_postpartum12m") is True:
        lines.append("- 임신/출산 12개월 이내")

    return "\n".join(lines)


def _format_collection_ctx(items: Optional[List[Dict[str, Any]]]) -> str:
    """
    단일 컬렉션(triples 리스트)을 텍스트로 요약.
    (기존 flat 리스트용 포맷)
    """
    if not items:
        return ""
    out = []
    for it in items[:8]:
        if "error" in it:
            continue
        segs = []
        if it.get("predicate"):
            segs.append(f"[{it['predicate']}]")
        if it.get("object"):
            segs.append(it["object"])
        out.append("- " + " ".join(segs))
    return "\n".join(out)


def _format_collection_layers(layers: Optional[Dict[str, Any]]) -> str:
    """
    collection_layers (L0/L1/L2)를 사람이 보기 좋게 포맷.
    - L0: 이번 턴
    - L1: 이번 세션 누적
    - L2: 과거(DB)
    """
    if not isinstance(layers, dict):
        return ""

    out_blocks: List[str] = []

    def _add_layer(name: str, label: str):
        layer = layers.get(name)
        if not isinstance(layer, dict):
            return
        triples = layer.get("triples")
        if not isinstance(triples, list) or not triples:
            return
        body = _format_collection_ctx(triples)
        if not body:
            return
        out_blocks.append(f"[Collection {label}]\n{body}")

    _add_layer("L0", "L0 - 이번 턴 정보")
    _add_layer("L1", "L1 - 이번 세션 누적 정보")
    _add_layer("L2", "L2 - 과거(DB) 정보")

    return "\n\n".join(out_blocks)


def _format_documents(items: Optional[List[Dict[str, Any]]]) -> str:
    if not items:
        return ""
    out: List[str] = []

    for idx, doc in enumerate(items[:6], start=1):
        if not isinstance(doc, dict):
            continue

        title = doc.get("title") or doc.get("doc_id") or f"문서 {idx}"
        source = doc.get("source")
        score = doc.get("score")
        url = doc.get("url")
        snippet = doc.get("snippet") or ""

        header = f"{idx}. {title}"
        if source:
            header += f" ({source})"
        if score:
            try:
                header += f" [score={float(score):.3f}]"
            except Exception:
                header += f" [score={score}]"

        out.append(f"- {header}")
        out.append(f"  > {snippet.strip()}")

        if url:
            out.append(f"  출처: {url}")

    return "\n".join(out)


def _build_user_prompt(
    input_text: str,
    used: str,
    profile_ctx: Optional[Dict[str, Any]],
    collection_layers: Optional[Dict[str, Any]],
    summary: Optional[str] = None,
    documents: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Gemini에 넘길 user prompt 구성.
    - collection_layers(L0/L1/L2)를 명시적으로 보여준다.
    """
    prof_block = _format_profile_ctx(profile_ctx)
    layers_block = _format_collection_layers(collection_layers)
    doc_block = _format_documents(documents)
    summary_block = (summary or "").strip()

    lines: List[str] = [f"사용자 질문:\n{input_text.strip()}"]
    lines.append(f"\n[Retrieval 사용: {used}]")

    if prof_block:
        lines.append("\n[Profile 컨텍스트]\n" + prof_block)
    if layers_block:
        lines.append("\n[Collection 계층 컨텍스트]\n" + layers_block)
    if summary_block:
        lines.append("\n[Rolling Summary]\n" + summary_block)
    if doc_block:
        lines.append("\n[RAG 문서 스니펫]\n" + doc_block)

    # SYSTEM_PROMPT에서 출력 형식을 이미 정의했으므로
    # 여기서는 별도 출력 형식 요구사항은 넣지 않는다.
    return "\n".join(lines)

# ───────────────────────────────────────────────────────────
# Gemini LLM 호출
# ───────────────────────────────────────────────────────────

def run_answer_llm(
    input_text: str,
    used: str,
    profile_ctx: Optional[Dict[str, Any]],
    collection_layers: Optional[Dict[str, Any]],
    summary: Optional[str] = None,
    documents: Optional[List[Dict[str, Any]]] = None,
) -> str:

    user_prompt = _build_user_prompt(
        input_text,
        used,
        profile_ctx,
        collection_layers,
        summary=summary,
        documents=documents,
    )

    model = genai.GenerativeModel(ANSWER_MODEL)

    # Gemini 2.x 에서는 system role 불가능 → system 프롬프트를 문자열 결합으로 넣어야 함
    full_prompt = SYSTEM_PROMPT + "\n\n" + user_prompt

    try:
        resp = model.generate_content(
            full_prompt,
            generation_config={"temperature": 0.3},
        )

        # 1) resp.text가 있을 경우
        if hasattr(resp, "text") and resp.text:
            return resp.text.strip()

        # 2) Gemini 2.x 표준 구조: candidates[].content.parts[].text
        if getattr(resp, "candidates", None):
            cand = resp.candidates[0]
            if getattr(cand, "content", None) and getattr(cand.content, "parts", None):
                text = "".join(
                    part.text
                    for part in cand.content.parts
                    if hasattr(part, "text")
                )
                return text.strip()

        return str(resp)

    except Exception as e:
        print("🔥🔥 [Gemini ERROR]", e)
        raise

# ───────────────────────────────────────────────────────────
# 메시지 컨텍스트 추출
# ───────────────────────────────────────────────────────────

def _extract_context_from_messages(messages: List[Message]) -> Dict[str, Any]:
    for msg in reversed(messages or []):
        if msg.get("role") != "tool":
            continue
        if msg.get("content") != "[context_assembler] prompt_ready":
            continue
        meta = msg.get("meta") or {}
        ctx = meta.get("context")
        if isinstance(ctx, dict):
            return ctx
    return {}


def _last_user_content(messages: List[Message]) -> str:
    for msg in reversed(messages or []):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""


def _infer_used_flag(profile_ctx: Any, collection_ctx: Any, documents: Any) -> str:
    has_profile = isinstance(profile_ctx, dict) and bool(profile_ctx)
    has_collection = isinstance(collection_ctx, list) and bool(collection_ctx)
    has_docs = isinstance(documents, list) and bool(documents)
    if has_profile and (has_collection or has_docs):
        return "BOTH"
    if has_profile:
        return "PROFILE"
    if has_collection or has_docs:
        return "COLLECTION"
    return "NONE"


def _safe_json(value: Any, limit: int = 400) -> str:
    if not value:
        return "없음"
    try:
        text = json.dumps(value, ensure_ascii=False)
    except Exception:
        text = str(value)
    return text[:limit] + ("..." if len(text) > limit else "")


# ───────────────────────────────────────────────────────────
# Fallback 메시지
# ───────────────────────────────────────────────────────────

def _build_fallback_text(
    used: str,
    profile_ctx: Any,
    collection_ctx: Any,
    documents: Any,
    summary: Optional[str],
) -> str:
    return (
        "죄송해요. 응답 생성 중 문제가 발생했어요.\n\n"
        "## 근거(요약)\n"
        f"- Retrieval 사용: {used}\n"
        f"- Summary: {(summary or '없음')[:400]}\n"
        f"- Profile: {_safe_json(profile_ctx)}\n"
        f"- Collection: {_safe_json(collection_ctx)}\n"
        f"- Documents: {_safe_json(documents)}\n"
        "필요 시 다시 시도해 주세요."
    )


# ───────────────────────────────────────────────────────────
# 메인 answer 노드
# ───────────────────────────────────────────────────────────

def answer(state: GraphState) -> Dict[str, Any]:
    messages: List[Message] = list(state.get("messages") or [])
    retrieval = state.get("retrieval") or {}
    ctx = _extract_context_from_messages(messages)

    profile_ctx = ctx.get("profile") or retrieval.get("profile_ctx")
    collection_ctx = ctx.get("collection") or retrieval.get("collection_ctx")

    # flat 리스트 (기존 로직 유지: fallback/used flag용)
    if isinstance(collection_ctx, dict) and "triples" in collection_ctx:
        collection_ctx_list = collection_ctx["triples"]
    elif isinstance(collection_ctx, list):
        collection_ctx_list = collection_ctx
    else:
        collection_ctx_list = None

    documents = ctx.get("documents") or retrieval.get("rag_snippets")
    summary = ctx.get("summary") or state.get("rolling_summary")

    input_text = (
        (state.get("user_input") or state.get("input_text") or "").strip()
        or _last_user_content(messages).strip()
    )

    # collection_layers: context → retrieval → state 순으로 조회
    collection_layers = (
        ctx.get("collection_layers")
        or retrieval.get("collection_layers")
        or {
            "L0": state.get("collection_layer_L0"),
            "L1": state.get("collection_layer_L1"),
            "L2": state.get("collection_layer_L2"),
        }
    )

    used = (retrieval.get("used") or "").strip().upper()
    if not used:
        used = _infer_used_flag(profile_ctx, collection_ctx_list, documents)

    try:
        text = run_answer_llm(
            input_text,
            used,
            profile_ctx,
            collection_layers,
            summary=summary,
            documents=documents,
        )
    except Exception:
        text = _build_fallback_text(
            used,
            profile_ctx,
            collection_ctx_list,
            documents,
            summary,
        )

    citations = {
        "profile": profile_ctx,
        "collection": collection_ctx_list,
        "documents": documents,
    }

    assistant_message: Message = {
        "role": "assistant",
        "content": text,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "meta": {
            "model": ANSWER_MODEL,
            "used": used,
            "citations": {
                "profile": bool(profile_ctx),
                "collection_count": len(collection_ctx_list or []),
                "document_count": len(documents or []),
            },
        },
    }

    return {
        "answer": {
            "text": text,
            "citations": citations,
            "used": used,
        },
        "messages": [assistant_message],
    }


def answer_llm_node(state: GraphState) -> Dict[str, Any]:
    return answer(state)
