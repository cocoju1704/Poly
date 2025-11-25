# app/api/v1/chat.py
from __future__ import annotations

from typing import Optional, Dict, Any, List, Generator
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field

from app.agents.new_pipeline import build_graph
from app.db.db_core import get_db_connection
from app.db import chat_repository
from app.api.v1.user import get_current_active_user

router = APIRouter()

# ⭐ 전역 캐시 (싱글톤 패턴)
_graph_app = None
_graph_init_error = None  # 초기화 에러 저장


def get_graph_app():
    """LangGraph 인스턴스를 lazy하게 로드 (첫 호출 시 1회만 생성)"""
    global _graph_app, _graph_init_error

    # 이미 초기화 실패한 경우 즉시 에러
    if _graph_init_error:
        raise _graph_init_error

    if _graph_app is None:
        try:
            print("🔧 [INFO] LangGraph 워크플로우 초기화 중...")
            _graph_app = build_graph()
            print("✅ [INFO] LangGraph 초기화 완료")
        except Exception as e:
            _graph_init_error = HTTPException(
                status_code=503, detail=f"LangGraph 초기화 실패: {str(e)}"
            )
            print(f"🔥 [ERROR] LangGraph 초기화 실패: {e}")
            raise _graph_init_error

    return _graph_app


# ─────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    profile_id: Optional[int] = None  # 👈 프로필 ID 추가
    user_input: str
    user_action: str = "none"
    client_meta: Dict[str, Any] = {}


class ChatDebug(BaseModel):
    router_decision: Optional[str] = None
    used_rag: Optional[bool] = None
    policy_ids: List[int] = []


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    session_ended: bool
    save_result: Optional[str]
    debug: ChatDebug


# ----------------------------------------------------
# 💡 [신규] 대화 저장 모델 정의 11.20
# ----------------------------------------------------


class Message(BaseModel):
    """채팅 메시지 구조 (프론트엔드의 st.session_state.messages와 일치)"""

    id: str = Field(..., description="메시지 고유 ID (UUID)")
    role: str = Field(..., description="역할 (user, assistant)")
    content: str = Field(..., description="메시지 내용")
    timestamp: float = Field(..., description="타임스탬프")
    # 정책 카드는 저장 시 필수 요소는 아닐 수 있으므로 Optional로 처리
    policies: Optional[List[Dict[str, Any]]] = None


class SaveChatRequest(BaseModel):
    """대화 저장 요청 본문 모델"""

    conversation_id: Optional[str] = None  # 💡 [추가] 기존 대화 ID
    profile_id: int = Field(..., description="선택된 사용자 프로필 ID")
    messages: List[Message] = Field(..., description="저장할 전체 메시지 목록")


# ─────────────────────────────────────
# /api/v1/chat/save 엔드포인트 (신규)
# ─────────────────────────────────────
@router.post("/chat/save", status_code=status.HTTP_201_CREATED)
async def save_chat_history(
    request: SaveChatRequest,
    current_user: Dict[str, Any] = Depends(get_current_active_user),  # ✅ 표준 인증 의존성으로 교체
    db_conn: Any = Depends(get_db_connection),
):
    """
    현재 대화 세션의 전체 메시지 내용을 DB에 영구적으로 저장합니다.
    """
    # 1. 인증 확인 및 사용자 ID 추출
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이 기능을 사용하려면 인증된 사용자여야 합니다.",
        )

    user_id = current_user.get("id")  # ✅ get_current_active_user 반환값에 맞춰 'id' 키 사용

    # 2. 프로필 유효성 검사
    if not request.profile_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="저장할 대화의 프로필 ID가 누락되었습니다.",
        )

    if not db_conn:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="데이터베이스에 연결할 수 없습니다.",
        )

    try:
        # ✅ [수정] Pydantic 모델 리스트를 딕셔너리 리스트로 변환
        messages_as_dicts = [msg.model_dump() for msg in request.messages]

        with db_conn.cursor() as cursor:
            conversation_id = chat_repository.save_full_conversation(
                cursor=cursor,
                profile_id=request.profile_id,
                conversation_id=request.conversation_id,  # 💡 [추가] ID 전달
                # 딕셔너리로 변환된 메시지 리스트를 전달
                messages=messages_as_dicts,
            )
            db_conn.commit()
            return {"message": "대화 내용 저장 완료", "conversation_id": conversation_id}
    except Exception as e:
        if db_conn:
            db_conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"대화 저장 중 서버 오류 발생: {e}",
        )


# ─────────────────────────────────────
# /api/chat
# ─────────────────────────────────────
@router.post("/chat/stream", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """
    채팅 메시지를 처리하고 응답을 반환합니다.

    첫 호출 시 LangGraph 워크플로우를 초기화합니다 (약 1-2초 소요).
    이후 호출은 캐시된 인스턴스를 사용하여 즉시 처리됩니다.
    """
    # A) 세션 ID 생성/유지
    session_id = req.session_id or f"sess-{uuid4().hex}"
    print(f"🔎 [DEBUG] Received profile_id from Streamlit: {req.profile_id}")
    # B) LangGraph에 넘길 초기 state
    base_end_session = req.user_action in ("reset_save", "reset_drop")
    init_state: Dict[str, Any] = {
        "session_id": session_id,
        "user_input": req.user_input,
        "user_action": req.user_action,
        "end_session": base_end_session,
        "client_meta": req.client_meta,
        "profile_id": req.profile_id,  # ⭐ 여기 명시적으로 넣기
    }
    print(f"🔎 [DEBUG] init_state.profile_id = {init_state.get('profile_id')}")
    # C) 세션 기반 체크포인트 사용
    config = {"configurable": {"thread_id": session_id}}

    # ⭐ D) LangGraph 실행 (lazy loading)
    try:
        graph_app = get_graph_app()
    except HTTPException as e:
        # 초기화 실패 시 사용자에게 명확한 에러 메시지
        raise e

    out_state: Dict[str, Any] = graph_app.invoke(init_state, config=config)

    # ─────────────────────────────────────
    # 답변 텍스트 추출
    # ─────────────────────────────────────
    raw_answer = out_state.get("answer")
    if isinstance(raw_answer, dict):
        answer_text = raw_answer.get("text") or ""
    else:
        answer_text = raw_answer or ""

    # ─────────────────────────────────────
    # 세션 종료 여부
    # ─────────────────────────────────────
    session_ended = bool(
        req.user_action in ("reset_save", "reset_drop")
        or out_state.get("end_session") is True
    )

    # ─────────────────────────────────────
    # persist_pipeline 결과
    # ─────────────────────────────────────
    persist_result = out_state.get("persist_result") or {}
    if persist_result:
        save_result = "ok" if persist_result.get("ok") else "error"
    else:
        save_result = None

    # ─────────────────────────────────────
    # 디버그 정보
    # ─────────────────────────────────────
    retrieval = out_state.get("retrieval") or {}
    rag_snippets = retrieval.get("rag_snippets") or []

    router_decision = (
        "save"
        if req.user_action == "save"
        else (
            req.user_action
            if req.user_action in ("reset_save", "reset_drop")
            else "normal"
        )
    )

    used_rag = retrieval.get("used_rag")

    policy_ids: List[int] = []
    for doc in rag_snippets:
        doc_id = doc.get("doc_id")
        if isinstance(doc_id, int):
            policy_ids.append(doc_id)

    debug = ChatDebug(
        router_decision=router_decision,
        used_rag=bool(used_rag),
        policy_ids=policy_ids,
    )

    # ─────────────────────────────────────
    # 최종 응답
    # ─────────────────────────────────────
    return ChatResponse(
        session_id=session_id,
        answer=answer_text,
        session_ended=session_ended,
        save_result=save_result,
        debug=debug,
    )
