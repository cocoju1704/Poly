## 프로젝트 개요

이 프로젝트는 Streamlit 기반의 프론트엔드와 FastAPI 기반의 백엔드를 사용하여 사용자 맞춤형 복지/의료 정책 정보를 제공하는 AI 챗봇입니다. LLM(Large Language Model)을 활용하여 사용자 질문에 답변하고, PostgreSQL 데이터베이스를 통해 사용자 정보 및 프로필을 관리합니다.

## 전체 프로젝트 구조

```
Project/
├── app/                   # FastAPI 백엔드 애플리케이션
│   ├── api/
│   │   └── v1/
│   │       ├── chat.py    # 챗봇 API 라우터 (LLM 응답 생성)
│   │       └── user.py    # 사용자 인증/프로필 API 라우터 (회원가입, 로그인, 프로필 관리)
│   ├── backend/
│   │   ├── llm_manager.py # LangChain 및 LLM(OpenAI) 관리 로직
│   │   └── models.py      # LLM 요청/응답 관련 Pydantic 모델
│   ├── db/
│   │   └── database.py    # PostgreSQL 데이터베이스 연결 및 CRUD 함수
│   ├── main.py            # FastAPI 앱 초기화, 라우터 등록, CORS 설정, 환경 변수 로드
│   ├── auth.py            # JWT 토큰 생성 및 검증 유틸리티
│   └── schemas.py         # Pydantic 스키마 (사용자, 프로필, 토큰 등 데이터 유효성 검사)
│
├── app/frontend/          # Streamlit 프론트엔드 애플리케이션
│   ├── app.py             # 메인 앱 (Streamlit 진입점)
│   ├── src/               # 프론트엔드 소스 코드
│   │   ├── pages/         # 페이지별 UI 및 핸들러 로직
│   │   │   ├── chat.py    # 챗봇 UI 및 대화 처리
│   │   │   ├── login.py   # 로그인/회원가입 UI 및 로직
│   │   │   ├── my_page.py # 마이페이지 (프로필 관리) UI 및 로직
│   │   │   └── settings.py# 설정 UI 및 로직 (비밀번호 변경, 회원 탈퇴 등)
│   │   ├── services/
│   │   │   └── backend.py # FastAPI 백엔드 API 호출 서비스 (HTTP 클라이언트 역할)
│   │   ├── utils/         # 공통 유틸리티
│   │   │   ├── session_manager.py # Streamlit 세션 상태 저장/로드
│   │   │   └── template_loader.py # HTML 템플릿 로드 유틸리티
│   │   ├── widgets/       # 재사용 가능한 UI 위젯
│   │   │   └── sidebar.py # 사이드바 UI
│   │   └── state_manger.py# Streamlit 세션 상태 초기화
│   │
│   ├── templates/         # HTML 템플릿 파일
│   │   └── components/    # 컴포넌트별 HTML 조각
│   └── styles/            # CSS 스타일 파일
│       └── components/    # 컴포넌트별 CSS 조각
│
└── .env                   # 환경 변수 (API 키, DB 연결 정보 등)
```

## 아키텍처

이 프로젝트는 클라이언트-서버 아키텍처를 따르며, 프론트엔드와 백엔드가 명확히 분리되어 있습니다.

### 1. 프론트엔드 (Streamlit)
-   **위치**: `app/frontend/`
-   **기술**: Streamlit (Python)
-   **기능**:
    -   사용자 인터페이스 (UI) 렌더링
    -   사용자 입력 처리 및 상태 관리
    -   로그인, 회원가입, 프로필 관리, 챗봇 대화 등 모든 데이터 요청을 FastAPI 백엔드 API에 위임
    -   `app/frontend/src/services/backend.py`를 통해 백엔드와 통신

### 2. 백엔드 (FastAPI)
-   **위치**: `app/`
-   **기술**: FastAPI (Python)
-   **기능**:
    -   RESTful API 엔드포인트 제공
    -   사용자 인증 및 권한 부여 (JWT 기반)
    -   사용자 프로필 데이터 관리 (CRUD)
    -   LLM(Large Language Model) 연동 및 응답 생성 (스트리밍 지원)
    -   PostgreSQL 데이터베이스와의 모든 상호작용 처리

### 3. 데이터베이스 (PostgreSQL)
-   **위치**: `app/db/database.py` (백엔드에서 접근)
-   **기술**: PostgreSQL, `psycopg2`
-   **기능**:
    -   사용자 계정 정보 (이메일, 비밀번호 해시, UUID) 저장
    -   사용자 프로필 정보 (이름, 생년월일, 성별, 거주지, 소득 수준 등) 저장
    -   모든 데이터베이스 CRUD(Create, Read, Update, Delete) 작업 수행

### 4. LLM (Large Language Model)
-   **위치**: `app/backend/llm_manager.py` (백엔드에서 관리)
-   **기술**: LangChain, OpenAI API
-   **기능**:
    -   사용자 질문과 프로필 정보를 바탕으로 맞춤형 답변 생성
    -   스트리밍 응답 지원

## 실행 흐름 요약

1.  **서버 실행**:
    -   **백엔드**: 프로젝트 루트 디렉토리에서 `uvicorn app.main:app --reload --port 8000` 명령어로 FastAPI 서버를 실행합니다. (`.env` 파일의 환경 변수가 `app/main.py`에서 로드됩니다.)
    -   **프론트엔드**: `app/frontend` 디렉토리에서 `streamlit run app.py` 명령어로 Streamlit 앱을 실행합니다.

2.  **사용자 인증 (회원가입/로그인)**:
    -   프론트엔드(`app/frontend/src/pages/login.py`)의 UI에서 사용자가 로그인/회원가입 정보를 입력합니다.
    -   프론트엔드의 `app/frontend/src/services/backend.py` 모듈은 FastAPI 백엔드의 `/api/v1/user/register` 또는 `/api/v1/user/login` 엔드포인트로 HTTP 요청을 보냅니다.
    -   백엔드(`app/api/v1/user.py`)는 요청을 받아 `app/db/database.py`를 통해 DB에서 사용자 정보를 검증하거나 생성합니다.
    -   인증 성공 시, 백엔드는 JWT(JSON Web Token)를 생성하여 프론트엔드로 반환하고, 프론트엔드는 이 토큰을 세션에 저장하여 이후 요청에 사용합니다.

3.  **프로필 관리**:
    -   프론트엔드(`app/frontend/src/pages/my_page.py`)에서 사용자가 프로필을 조회, 추가, 수정, 삭제합니다.
    -   `backend_service.py`를 통해 백엔드의 `/api/v1/user/profile` 엔드포인트로 HTTP 요청을 보냅니다.
    -   백엔드는 JWT 토큰을 검증하여 인증된 사용자만 프로필을 관리할 수 있도록 합니다.

4.  **챗봇 메시지 전송**:
    -   프론트엔드(`app/frontend/src/pages/chat.py`)에서 사용자가 메시지를 입력하면, `backend_service.py`를 통해 백엔드의 `/api/v1/chat/stream` 엔드포인트로 스트리밍 요청을 보냅니다.
    -   요청에는 대화 이력, 사용자 메시지, 현재 활성화된 프로필 정보가 포함됩니다.
    -   백엔드(`app/api/v1/chat.py`)는 `app/backend/llm_manager.py`를 호출하여 LangChain과 OpenAI 모델을 통해 응답을 생성합니다.
    -   생성된 응답은 FastAPI의 `StreamingResponse`를 통해 프론트엔드로 실시간 전송되며, UI에 표시됩니다.

5.  **데이터 관리**:
    -   모든 사용자 및 프로필 관련 데이터는 PostgreSQL 데이터베이스에 저장됩니다.
    -   백엔드의 `app/db/database.py` 모듈이 DB와의 모든 상호작용(CRUD)을 담당합니다.
    -   **프론트엔드는 데이터베이스에 직접 접근하지 않으며**, 항상 FastAPI 백엔드 API를 통해서만 데이터를 요청하고 수정합니다.

## 주요 변경 사항 요약

### 1. 아키텍처 분리 및 역할 명확화
-   **프론트엔드 (Streamlit)**: UI 렌더링 및 사용자 상호작용에만 집중하며, 모든 데이터 관련 로직은 백엔드 API 호출로 전환되었습니다. `app/frontend/src/pages/login.py`, `app/frontend/src/pages/my_page.py`, `app/frontend/src/pages/settings.py`, `app/frontend/app.py` 등에서 데이터베이스 직접 접근 코드가 `app/frontend/src/services/backend.py`를 통한 API 호출로 대체되었습니다.
-   **백엔드 (FastAPI)**: 인증, 프로필 관리, LLM 연동, 데이터베이스 상호작용 등 모든 비즈니스 로직을 담당하는 RESTful API 서버로 기능이 통합되었습니다.

### 2. 파일 구조 및 모듈 정리
-   **`app/backend/api_server.py` 삭제**: `app/main.py`를 단일 진입점으로 사용하여 서버 실행의 혼란을 제거했습니다.
-   **`app/schemas.py` 통합 및 개선**: 사용자, 프로필, 토큰 관련 Pydantic 모델들이 `app/schemas.py`로 통합되어 일관성을 확보하고, `UserProfileUpdate` 스키마가 제거되었습니다.
-   **`app/api/v1/user.py` 구현**: 사용자 인증 및 프로필 관리 API 엔드포인트가 실제 데이터베이스 연동 로직과 함께 구현되었습니다.
-   **`app/frontend/src/sign.py` 삭제**: 역할이 모호하고 중복되던 파일이 제거되었습니다.
-   **`app/frontend/src/services/backend.py` 확장**: 로그인, 회원가입, 프로필 조회/수정/삭제 등 사용자 관련 백엔드 API 호출 함수들이 추가되었습니다.
-   **`app/main.py` 환경 변수 로드 시점 수정**: `load_dotenv()` 호출이 다른 모듈 import 전에 이루어지도록 최상단으로 이동하여 환경 변수 로드 문제를 해결했습니다.

### 3. 데이터베이스 관련 파일 정리 (벡터 검색 기능 제거)
-   **다음 파일들이 삭제되었습니다**:
    -   `app/db/policy_repository.py` (벡터 검색 및 RAG 관련)
    -   `app/db/user_repository.py` (기존 `database.py`와 중복되는 사용자 관련 DB 로직)
    -   `app/db/normalizer.py` (데이터 정규화 로직, `database.py`로 통합)
    -   `app/db/db_core.py` (기존 `database.py`와 중복되는 DB 연결 로직)
    -   `app/db/config.py` (환경 변수 로드 및 DB 설정, `main.py` 및 `database.py`로 통합)
-   **`app/db/database.py`**: 모든 PostgreSQL 데이터베이스 CRUD 및 사용자 인증 관련 로직을 담당하도록 통합 및 개선되었습니다.

### 4. 기타 개선 사항
-   `app/auth.py`에서 JWT 토큰의 `sub` 필드에 `username` 대신 `email`을 사용하도록 변경되었습니다.
-   FastAPI의 의존성 주입(`Depends`)을 활용하여 DB 세션(`get_db`)을 올바르게 관리하도록 `app/db/database.py`에 함수가 추가되었습니다.

이러한 변경을 통해 프로젝트는 더욱 견고하고 유지보수하기 쉬운 구조를 갖추게 되었습니다.