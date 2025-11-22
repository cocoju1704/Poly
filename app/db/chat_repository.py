"""대화 및 메시지 저장소 관련 기능을 포함하는 모듈 11.20 수정"""

import uuid
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging

# 로깅 설정
logger = logging.getLogger(__name__)


class ConversationSaveError(Exception):
    """대화 저장 중 발생하는 사용자 정의 예외"""

    pass


def save_full_conversation(
    cursor: Any,  # user_id는 conversations 테이블에 직접 저장되지 않으므로 제거
    profile_id: int,
    conversation_id: Optional[str],  # 💡 [수정] conversation_id를 인자로 받음
    messages: List[Dict[str, Any]],
) -> str:
    """
    하나의 트랜잭션으로 conversations 테이블과 messages 테이블에 데이터를 저장합니다.

    Args:
        cursor: DB 커서 객체
        user_id: 현재 인증된 사용자 ID
        conversation_id: 기존 대화 ID (없으면 새로 생성)
        profile_id: 대화에 사용된 프로필 ID
        messages: 프론트엔드에서 받은 전체 메시지 목록

    Returns:
        저장된 대화의 conversation_id (UUID 문자열)

    Raises:
        ConversationSaveError: DB 저장 실패 시 발생
    """
    if not messages:
        return "no_messages_to_save"

    # 1. conversation_id가 없으면 새로 생성, 있으면 기존 ID 사용
    is_new_conversation = not conversation_id
    if is_new_conversation:
        conversation_id = str(uuid.uuid4())
    else:
        # 기존 메시지는 삭제 후 다시 삽입 (UPSERT보다 간단한 구현)
        cursor.execute("DELETE FROM public.messages WHERE conversation_id = %s", (conversation_id,))

    # 2. 메타데이터 준비
    now = datetime.now(timezone.utc)
    started_at = messages[0].get("timestamp", now.timestamp())
    ended_at = messages[-1].get("timestamp", now.timestamp())

    # JSONB 필드 처리: messages의 policies를 meta 필드로 옮기고 JSON 직렬화
    message_records = []
    for i, msg in enumerate(messages):
        # policies를 meta JSONB 필드에 포함
        meta_data = {}
        if "policies" in msg and msg["policies"] is not None:
            meta_data["policies"] = msg["policies"]

        # tool_name 추출 (role이 'tool'일 경우)
        tool_name = msg.get("tool_name") or (
            msg["content"].split(":")[0].strip()
            if msg["role"] == "tool" and ":" in msg["content"]
            else None
        )

        # 'token_usage'가 있으면 JSONB로 저장
        token_usage_data = msg.get("token_usage")

        message_records.append(
            {
                "id": msg.get("id", str(uuid.uuid4())),
                "conversation_id": conversation_id,
                "turn_index": i,  # 순서는 배열 인덱스를 사용
                "role": msg["role"],
                "content": msg["content"],
                "tool_name": tool_name,
                "token_usage": token_usage_data,  # JSONB 필드
                "meta": meta_data,  # JSONB 필드
                "created_at": datetime.fromtimestamp(
                    msg.get("timestamp", now.timestamp()), tz=timezone.utc
                ),
            }
        )

    # 3. DB 저장 로직 시작 (트랜잭션 권장)
    try:
        if is_new_conversation:
            # 3-1. (신규) conversations 테이블에 새 레코드 삽입
            cursor.execute(
                """
                INSERT INTO public.conversations 
                    (id, profile_id, started_at, ended_at, summary, model_stats, created_at)
                VALUES 
                    (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    conversation_id,
                    profile_id,
                    datetime.fromtimestamp(started_at, tz=timezone.utc),
                    datetime.fromtimestamp(ended_at, tz=timezone.utc),
                    json.dumps({"initial_prompt": messages[0].get("content")}),
                    json.dumps({}),
                    now,
                ),
            )
        else:
            # 3-1. (업데이트) 기존 conversations 레코드의 종료 시간 등 업데이트
            cursor.execute(
                """
                UPDATE public.conversations
                SET ended_at = %s,
                    updated_at = %s
                WHERE id = %s
                """,
                (
                    datetime.fromtimestamp(ended_at, tz=timezone.utc),
                    now,
                    conversation_id,
                ),
            ),

        # 3-2. messages 테이블에 모든 메시지 레코드 삽입
        for record in message_records:
            # PostgreSQL 드라이버에 따라 JSON/JSONB 삽입 방식이 다를 수 있음 (여기서는 json.dumps 사용)
            cursor.execute(
                """
                INSERT INTO public.messages 
                    (id, conversation_id, turn_index, role, content, tool_name, token_usage, meta, created_at)
                VALUES 
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    record["id"],
                    record["conversation_id"],
                    record["turn_index"],
                    record["role"],
                    record["content"],
                    record["tool_name"],
                    (
                        json.dumps(record["token_usage"])
                        if record["token_usage"]
                        else None
                    ),
                    json.dumps(record["meta"]),
                    record["created_at"],
                ),
            )
            
        # 3-3. [제거] collections 테이블 저장 로직
        # 이 로직은 LangGraph의 persist_pipeline 노드로 이동하여 처리하는 것이 더 적합합니다.
        # chat_repository는 순수하게 대화 내용 저장에만 집중합니다.

        return conversation_id

    except Exception as e:
        logger.exception("DB 저장 트랜잭션 실패")  # 스택 트레이스 로깅
        # 로깅 필요
        raise ConversationSaveError(f"DB 저장 트랜잭션 실패: {e}")
