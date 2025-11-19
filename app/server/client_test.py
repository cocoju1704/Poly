# client_test.py
# -*- coding: utf-8 -*-
import requests
import json

API_URL = "http://127.0.0.1:8000/api/chat"

def send_chat(
    session_id=None,
    user_input="",
    user_action="none"
):
    payload = {
        "session_id": session_id,
        "user_input": user_input,
        "user_action": user_action,
        "client_meta": {
            "ui_lang": "ko",
            "app_version": "local-test"
        }
    }

    print("=== 요청 ===")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    r = requests.post(API_URL, json=payload)
    print("\n=== 응답 ===")
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))

    return r.json()


if __name__ == "__main__":
    # 1) 새 세션 시작
    res1 = send_chat(
        session_id=None,
        user_input="최근 3개월 병원비가 너무 많이 나왔어요."
    )

    # 2) 같은 세션 계속 사용
    session = res1["session_id"]

    res2 = send_chat(
        session_id=session,
        user_input="소득은 중위소득 50% 정도예요."
    )

    # 3) 저장만
    send_chat(session, user_input="", user_action="save")

    # 4) 저장하고 리셋
    send_chat(session, user_input="", user_action="reset_save")
