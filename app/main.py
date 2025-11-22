# app/main.py
from __future__ import annotations
from dotenv import load_dotenv
import os

load_dotenv()

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api.v1 import user, chat
from app.db.database import initialize_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("INFO:     애플리케이션 시작 - DB 초기화 조건 검사...")

    # 🔥 로컬에서는 initialize_db() 실행 금지
    #    서버에서는 ENV=production 일 때만 실행하도록 함
    env = os.getenv("ENV", "local")

    if env == "production":
        print("INFO:     [PRODUCTION] initialize_db() 실행합니다.")
        await initialize_db()  # ← 반드시 await
    else:
        print("INFO:     [LOCAL] initialize_db() 실행하지 않습니다.")

    yield
    # 종료 시 필요한 작업이 있으면 여기에 추가
    print("INFO:     애플리케이션 종료.")


app = FastAPI(
    title="HealthInformer API",
    description="Unified /api/chat endpoint to handle entire session flow.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 설정
app.include_router(user.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
