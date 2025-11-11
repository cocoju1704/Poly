## 프론트 엔드 구조
 stream_app/              # 프론트엔드 (Streamlit) 루트
 <br />
 │
  <br />
 ├── app.py               # 메인 앱 (진입점)
 <br />
 │
 <br />
 ├── src/                 # 소스 코드
 <br />
 │   ├── pages/           # 페이지별 UI 및 핸들러 로직
 <br />
 │   │   ├── auth.py
  <br />
 │   │   ├── chat.py
 <br />
 │   │   ├── my_page.py
  <br />
 │   │   └── settings.py
  <br />
 │   │
 <br />
 │   ├── widgets/         # 재사용 가능한 UI 위젯
 <br />
 │   │   └── sidebar.py
 <br />
 │   │
  <br />
 │   ├── utils/           # 공통 유틸리티
 <br />
 │   │   ├── session_manager.py
 <br />
 │   │   └── template_loader.py
 <br />
 │   │
 <br />
 │   ├── db/              # 데이터베이스 관련 로직
 <br />
 │   │   └── database.py
 <br />
 │   │
 <br />
 │   ├── backend_service.py # API 함수 래퍼 (DB와 UI의 중간 계층)
 <br />
 │   ├── llm_manager.py     # LangChain 및 LLM 관리
 <br />
 │   └── state_manger.py    # 세션 상태 초기화
 <br />
 │
 <br />
 ├── templates/           # HTML 템플릿
 <br />
 │   └── components/      # 컴포넌트별 HTML 조각
 <br />
 │
 <br />
 └── styles/              # CSS 스타일
     └── components/      # 컴포넌트별 CSS 조각


## 아키텍처

### 1. 프론트엔드 (Streamlit)
- **위치**: `app/stream_app/`
- **기술**: Streamlit (Python)
- **기능**:
  - 사용자 인터페이스
  - 로그인 / 회원가입
  - 챗봇 대화 인터페이스
  - 프로필 관리
  - 설정 관리

### 2. 모듈 구조 (분리된 페이지/로직)
- 진입점: `app/stream_app/app.py` (라우팅/초기화/전역상태 최소 유지)
- 인증: `app/stream_app/src/pages/auth.py` (로그인/회원가입 UI 및 상태)
- 마이페이지: `app/stream_app/src/pages/my_page.py` (프로필 조회/편집/추가/삭제)
- 설정: `app/stream_app/src/pages/settings.py` (비밀번호 변경/알림/회원탈퇴)
- 챗봇: `app/stream_app/src/pages/chat.py` (채팅 렌더링/메시지 전송/정책 카드 파싱)
- 백엔드 서비스: `app/stream_app/src/backend_service.py` (UI와 DB 로직을 연결하는 중간 계층)
- 데이터베이스: `app/stream_app/src/db/database.py` (PostgreSQL DB 연결 및 CRUD 함수)
- LLM 매니저: `app/stream_app/src/llm_manager.py` (ChatOpenAI 초기화 및 응답/스트리밍)

### 3. 실행 흐름 요약
1. **앱 시작**: `app.py`가 실행되며 `state_manger.py`와 `auth.py`의 초기화 함수를 호출하여 `st.session_state`를 설정합니다.
2. **세션 복원**: `session_manager.load_session()`을 통해 파일에 저장된 세션(사용자 UUID 등)이 있는지 확인하고, 있다면 로그인 상태를 복원합니다.
3. **라우팅**:
    - **비로그인 상태**: `render_landing_page()` 함수가 호출되어 랜딩 페이지와 함께 로그인/회원가입 탭을 표시합니다.
    - **로그인 상태**: `render_sidebar()`로 사이드바를 표시하고, `st.session_state`의 상태에 따라 `render_settings_modal()`, `render_my_page_modal()`, 또는 `render_chatbot_main()` 중 하나를 렌더링합니다.
4. **사용자 인증**:
    - **회원가입**: `auth.py`에서 사용자 정보를 받아 `database.py`의 `create_user_and_profile`을 호출하여 DB에 저장합니다.
    - **로그인**: `auth.py`에서 `username`과 `password`를 받아 `database.py`의 `get_user_password_hash`로 검증 후, `get_user_by_username`으로 사용자 정보(UUID 포함)를 가져와 세션에 저장합니다.
5. **챗봇 메시지 전송**:
    - `chat.py`의 `handle_send_message` 함수가 사용자 입력을 처리합니다.
    - `llm_manager.py`를 통해 현재 활성 프로필 정보를 포함한 프롬프트를 구성하고, `ChatOpenAI`의 스트리밍 응답을 받아 화면에 실시간으로 표시합니다.
6. **데이터 관리**:
    - 모든 사용자 및 프로필 관련 데이터 처리는 `id`(UUID)를 기본 식별자로 사용합니다.
    - `backend_service.py`는 UI 페이지와 `database.py` 사이의 중간 다리 역할을 하며, 직접적인 DB 호출을 추상화합니다.