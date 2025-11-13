# -*- coding: utf-8 -*-
"""
Streamlit 앱에서 직접 사용하는 데이터베이스 접근 계층 (PostgreSQL)
모든 CRUD 및 사용자 인증 관련 DB 로직을 포함합니다.
"""
import psycopg2
import os
import uuid
from typing import Optional, Dict, List, Tuple, Any
import logging
from contextlib import contextmanager
from dotenv import load_dotenv


# .env 파일에서 환경 변수 로드
load_dotenv()

# 로깅 설정
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 환경 변수에서 DB 연결 정보 로드
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

# ==============================================================================
# 1. DB 연결 및 컨텍스트 관리
# ==============================================================================


@contextmanager
def get_db_connection():
    """데이터베이스 연결 컨텍스트 매니저."""
    conn = None
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
        )
        yield conn
    except psycopg2.OperationalError as e:
        logger.error(f"PostgreSQL 연결 실패: {e}")
        yield None  # 연결 실패 시 None 반환
    except Exception as e:
        logger.error(f"데이터베이스 오류: {e}")
        yield None
    finally:
        if conn:
            conn.close()


def get_db():
    """FastAPI 의존성 주입을 위한 DB 세션 생성기"""
    conn = None
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
        )
        yield conn
    finally:
        if conn:
            conn.close()


def initialize_db():
    """
    DB에 'users' 및 'profiles' 테이블이 없으면 생성합니다.
    """
    with get_db_connection() as conn:
        if conn is None:
            logger.error("DB 초기화 실패: 연결할 수 없습니다.")
            return

        try:
            with conn.cursor() as cur:
                # 1. USERS 테이블 생성 (user_uuid는 UUID 타입)
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        user_uuid UUID UNIQUE NOT NULL,
                        username VARCHAR(255) UNIQUE NOT NULL,
                        password_hash VARCHAR(255) NOT NULL,
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        main_profile_id INTEGER NULL
                    );
                """
                )
                logger.info("Table 'users' checked/created.")

                # 2. PROFILES 테이블 생성
                # main_profile_id의 외래 키 제약 조건은 profiles 테이블 생성 후 추가해야 함
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS profiles (
                        profile_id SERIAL PRIMARY KEY,
                        user_uuid UUID NOT NULL,
                        profile_name VARCHAR(255) NOT NULL,
                        birth_date DATE,
                        gender VARCHAR(50),
                        location VARCHAR(255),
                        income_level INTEGER,
                        health_insurance VARCHAR(255),
                        basic_livelihood VARCHAR(255),
                        disability_level VARCHAR(50),
                        long_term_care VARCHAR(50),
                        pregnancy_status VARCHAR(50),
                        is_active BOOLEAN DEFAULT FALSE,
                        FOREIGN KEY (user_uuid) REFERENCES users (user_uuid) ON DELETE CASCADE
                    );
                """
                )
                logger.info("Table 'profiles' checked/created.")

                # 3. users 테이블의 main_profile_id에 외래 키 제약 조건 추가 (존재하지 않을 경우에만)
                try:
                    cur.execute(
                        """
                        ALTER TABLE users 
                        ADD CONSTRAINT fk_main_profile
                        FOREIGN KEY (main_profile_id) REFERENCES profiles (profile_id) 
                        ON DELETE SET NULL;
                    """
                    )
                    logger.info("Foreign key fk_main_profile added to 'users'.")
                except psycopg2.errors.DuplicateObject:
                    # 이미 제약 조건이 존재하는 경우 무시
                    pass

                conn.commit()

            logger.info("Database initialization complete.")
        except Exception as e:
            conn.rollback()
            logger.error(f"DB 초기화 중 오류 발생: {e}")


# ==============================================================================
# 2. 사용자 인증 및 계정 관리 (api_check_id_availability, api_signup 등 지원)
# ==============================================================================


def check_user_exists(username: str) -> bool:
    """아이디(username)를 사용하여 사용자 존재 여부를 확인합니다."""
    with get_db_connection() as conn:
        if conn is None:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
                return cur.fetchone() is not None
        except Exception as e:
            logger.error(f"check_user_exists 오류: {e}")
            return False


def get_user_password_hash(username: str) -> Optional[str]:
    """아이디(username)를 사용하여 저장된 비밀번호 해시를 가져옵니다."""
    with get_db_connection() as conn:
        if conn is None:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT password_hash FROM users WHERE username = %s", (username,)
                )
                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"get_user_password_hash 오류: {e}")
            return None


def get_user_uuid_by_username(username: str) -> Optional[str]:
    """아이디(username)를 사용하여 UUID를 가져옵니다 (로그인 성공 시 사용)."""
    with get_db_connection() as conn:
        if conn is None:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_uuid FROM users WHERE username = %s", (username,)
                )
                result = cur.fetchone()
                return str(result[0]) if result else None
        except Exception as e:
            logger.error(f"get_user_uuid_by_username 오류: {e}")
            return None


def create_user_and_profile(user_data: Dict[str, Any]) -> Tuple[bool, str]:
    """사용자 계정을 생성하고 초기 프로필을 저장합니다."""
    # user_data는 {username, password_hash, profile_name, ...}를 포함
    username = user_data.get("username")
    password_hash = user_data.get("password_hash")

    if not (username and password_hash):
        return False, "필수 사용자 정보가 누락되었습니다."

    new_uuid = str(uuid.uuid4())

    with get_db_connection() as conn:
        if conn is None:
            return False, "DB 연결 실패."

        try:
            with conn.cursor() as cur:
                # 1. 사용자 생성
                cur.execute(
                    "INSERT INTO users (user_uuid, username, password_hash) VALUES (%s, %s, %s)",
                    (new_uuid, username, password_hash),
                )

                # 2. 기본 프로필 생성
                profile_data = user_data.copy()
                profile_data["profile_name"] = profile_data.pop("name", "본인")

                # 프로필 데이터를 DB 컬럼에 맞게 매핑 및 삽입
                cur.execute(
                    """
                    INSERT INTO profiles (
                        user_uuid, profile_name, birth_date, gender, location, income_level, 
                        health_insurance, basic_livelihood, disability_level, 
                        long_term_care, pregnancy_status, is_active
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) 
                    RETURNING profile_id;
                """,
                    (
                        new_uuid,
                        profile_data.get("profile_name"),
                        profile_data.get("birthDate"),  # Date
                        profile_data.get("gender"),
                        profile_data.get("location"),
                        int(profile_data.get("incomeLevel") or 0),  # INTEGER
                        profile_data.get("healthInsurance"),
                        profile_data.get("basicLivelihood"),
                        profile_data.get("disabilityLevel"),
                        profile_data.get("longTermCare"),
                        profile_data.get("pregnancyStatus"),
                        True,  # 가입 시 생성되는 프로필은 활성화 상태
                    ),
                )

                # 3. 생성된 프로필 ID를 main_profile_id로 사용자 테이블에 업데이트
                main_profile_id = cur.fetchone()[0]
                cur.execute(
                    "UPDATE users SET main_profile_id = %s WHERE user_uuid = %s",
                    (main_profile_id, new_uuid),
                )

                conn.commit()
                return True, "회원가입 및 프로필 생성이 완료되었습니다."

        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            return False, "이미 존재하는 사용자 이름입니다."
        except Exception as e:
            conn.rollback()
            logger.error(f"create_user_and_profile 오류: {e}")
            return False, f"데이터베이스 오류: {e}"


def update_user_password(user_uuid: str, new_password_hash: str) -> Tuple[bool, str]:
    """사용자 비밀번호 해시를 업데이트합니다."""
    with get_db_connection() as conn:
        if conn is None:
            return False, "DB 연결 실패."
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET password_hash = %s WHERE user_uuid = %s",
                    (new_password_hash, user_uuid),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    return False, "사용자를 찾을 수 없습니다."
                conn.commit()
                return True, "비밀번호가 성공적으로 변경되었습니다."
        except Exception as e:
            conn.rollback()
            logger.error(f"update_user_password 오류: {e}")
            return False, "비밀번호 업데이트 중 오류가 발생했습니다."


def delete_user_account(user_uuid: str) -> Tuple[bool, str]:
    """사용자와 관련된 모든 정보를 삭제합니다 (profiles는 CASCADE로 삭제됨)."""
    with get_db_connection() as conn:
        if conn is None:
            return False, "DB 연결 실패."
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE user_uuid = %s", (user_uuid,))
                if cur.rowcount == 0:
                    conn.rollback()
                    return False, "사용자 계정을 찾을 수 없습니다."
                conn.commit()
                return True, "사용자 계정이 성공적으로 삭제되었습니다."
        except Exception as e:
            conn.rollback()
            logger.error(f"delete_user_account 오류: {e}")
            return False, "계정 삭제 중 오류가 발생했습니다."


# ==============================================================================
# 3. 프로필 관리 (api_get_user_info, api_save_profiles 등 지원)
# ==============================================================================


def _map_profile_row(row: Dict) -> Dict[str, Any]:
    """DB 행을 프론트엔드에서 사용하는 키 이름으로 변환합니다."""
    # DB의 snake_case를 front-end의 camelCase/Custom key로 매핑
    return {
        "id": row.get("profile_id"),  # 프로필 고유 ID (int)
        "name": row.get("profile_name"),  # 프로필 이름 (예: 본인, 아내)
        "birthDate": str(row["birth_date"]) if row.get("birth_date") else None,
        "gender": row.get("gender"),
        "location": row.get("location"),
        "incomeLevel": row.get("income_level"),
        "healthInsurance": row.get("health_insurance"),
        "basicLivelihood": row.get("basic_livelihood"),
        "disabilityLevel": row.get("disability_level"),
        "longTermCare": row.get("long_term_care"),
        "pregnancyStatus": row.get("pregnancy_status"),
        "isActive": row.get("is_active", False),
    }


def get_user_and_profile_by_id(user_uuid: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """사용자 UUID로 사용자 정보와 메인 프로필 정보를 조회합니다."""
    with get_db_connection() as conn:
        if conn is None:
            return False, None
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                # 사용자 정보 (username, main_profile_id) 및 메인 프로필 정보 조회
                cur.execute(
                    """
                    SELECT 
                        u.user_uuid, u.username, u.main_profile_id, p.*
                    FROM users u
                    LEFT JOIN profiles p ON u.main_profile_id = p.profile_id
                    WHERE u.user_uuid = %s;
                """,
                    (user_uuid,),
                )

                result = cur.fetchone()

                if not result:
                    return False, None

                user_info = dict(result)

                # 메인 프로필 정보를 _map_profile_row를 사용하여 매핑
                profile_info = (
                    _map_profile_row(user_info)
                    if user_info.get("main_profile_id")
                    else {}
                )

                # Streamlit `st.session_state["user_info"]`가 예상하는 최종 구조
                final_data = {
                    "user_uuid": str(user_info["user_uuid"]),
                    "username": user_info["username"],
                    "main_profile_id": user_info["main_profile_id"],
                    **profile_info,  # 메인 프로필 필드를 평탄화하여 포함
                }
                return True, final_data
        except Exception as e:
            logger.error(f"get_user_and_profile_by_id 오류: {e}")
            return False, None


def get_all_profiles_by_user_id(user_uuid: str) -> Tuple[bool, List[Dict[str, Any]]]:
    """사용자의 모든 프로필 목록을 조회합니다."""
    with get_db_connection() as conn:
        if conn is None:
            return False, []
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(
                    "SELECT * FROM profiles WHERE user_uuid = %s ORDER BY profile_id",
                    (user_uuid,),
                )
                rows = cur.fetchall()

                profiles_list = [_map_profile_row(dict(row)) for row in rows]
                return True, profiles_list
        except Exception as e:
            logger.error(f"get_all_profiles_by_user_id 오류: {e}")
            return False, []


def add_profile(user_uuid: str, profile_data: Dict[str, Any]) -> Tuple[bool, int]:
    """새로운 프로필을 추가합니다. 성공 시 프로필 ID를 반환합니다."""
    with get_db_connection() as conn:
        if conn is None:
            return False, 0
        try:
            with conn.cursor() as cur:
                # 프론트엔드의 키를 DB 컬럼에 맞게 매핑
                data = {
                    "profile_name": profile_data.get("name", "새 프로필"),
                    "birth_date": profile_data.get("birthDate"),
                    "gender": profile_data.get("gender"),
                    "location": profile_data.get("location"),
                    "income_level": int(profile_data.get("incomeLevel") or 0),
                    "health_insurance": profile_data.get("healthInsurance"),
                    "basic_livelihood": profile_data.get("basicLivelihood"),
                    "disability_level": profile_data.get("disabilityLevel"),
                    "long_term_care": profile_data.get("longTermCare"),
                    "pregnancy_status": profile_data.get("pregnancyStatus"),
                    "is_active": profile_data.get("isActive", False),
                }

                cur.execute(
                    """
                    INSERT INTO profiles (
                        user_uuid, profile_name, birth_date, gender, location, income_level, 
                        health_insurance, basic_livelihood, disability_level, 
                        long_term_care, pregnancy_status, is_active
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) 
                    RETURNING profile_id;
                """,
                    (
                        user_uuid,
                        data["profile_name"],
                        data["birth_date"],
                        data["gender"],
                        data["location"],
                        data["income_level"],
                        data["health_insurance"],
                        data["basic_livelihood"],
                        data["disability_level"],
                        data["long_term_care"],
                        data["pregnancy_status"],
                        data["is_active"],
                    ),
                )

                profile_id = cur.fetchone()[0]
                conn.commit()
                return True, profile_id
        except Exception as e:
            conn.rollback()
            logger.error(f"add_profile 오류: {e}")
            return False, 0


def update_profile(profile_id: int, profile_data: Dict[str, Any]) -> bool:
    """기존 프로필 정보를 업데이트합니다."""
    with get_db_connection() as conn:
        if conn is None:
            return False
        try:
            # 업데이트할 필드와 값 목록을 동적으로 구성
            set_clauses = []
            values = []

            # 프론트엔드 키를 DB 컬럼에 맞게 변환
            column_map = {
                "name": "profile_name",
                "birthDate": "birth_date",
                "gender": "gender",
                "location": "location",
                "incomeLevel": "income_level",
                "healthInsurance": "health_insurance",
                "basicLivelihood": "basic_livelihood",
                "disabilityLevel": "disability_level",
                "longTermCare": "long_term_care",
                "pregnancyStatus": "pregnancy_status",
                "isActive": "is_active",
            }

            for frontend_key, db_column in column_map.items():
                if frontend_key in profile_data:
                    # incomeLevel은 정수형으로 변환
                    value = profile_data[frontend_key]
                    if frontend_key == "incomeLevel":
                        value = int(value) if value is not None else None

                    set_clauses.append(f"{db_column} = %s")
                    values.append(value)

            if not set_clauses:
                logger.warning(f"업데이트할 데이터 없음: profile_id={profile_id}")
                return True  # 변경 사항이 없으므로 성공 처리

            values.append(profile_id)  # WHERE 절을 위한 profile_id

            sql = f"UPDATE profiles SET {', '.join(set_clauses)} WHERE profile_id = %s"

            with conn.cursor() as cur:
                cur.execute(sql, values)
                if cur.rowcount == 0:
                    conn.rollback()
                    return False  # 업데이트된 행 없음
                conn.commit()
                return True
        except Exception as e:
            conn.rollback()
            logger.error(f"update_profile 오류: {e}")
            return False


def delete_profile_by_id(profile_id: int) -> bool:
    """프로필 ID를 사용하여 프로필을 삭제합니다."""
    with get_db_connection() as conn:
        if conn is None:
            return False
        try:
            with conn.cursor() as cur:
                # 1. 삭제할 프로필이 어떤 사용자의 main_profile_id인지 확인
                cur.execute(
                    "SELECT user_uuid FROM users WHERE main_profile_id = %s",
                    (profile_id,),
                )
                user_result = cur.fetchone()

                # 2. 프로필 삭제
                # main_profile_id가 설정되어 있으면 외래 키 제약 조건(ON DELETE SET NULL)에 의해 users 테이블이 먼저 업데이트됩니다.
                cur.execute("DELETE FROM profiles WHERE profile_id = %s", (profile_id,))

                if cur.rowcount == 0:
                    conn.rollback()
                    return False

                conn.commit()
                return True
        except Exception as e:
            conn.rollback()
            logger.error(f"delete_profile_by_id 오류: {e}")
            return False


def update_user_main_profile_id(
    user_uuid: str, profile_id: Optional[int]
) -> Tuple[bool, str]:
    """사용자의 메인 프로필 ID를 업데이트합니다."""
    with get_db_connection() as conn:
        if conn is None:
            return False, "DB 연결 실패."
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET main_profile_id = %s WHERE user_uuid = %s",
                    (profile_id, user_uuid),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    return False, "사용자를 찾을 수 없거나 업데이트에 실패했습니다."
                conn.commit()
                return True, "기본 프로필 ID가 성공적으로 업데이트되었습니다."
        except Exception as e:
            conn.rollback()
            logger.error(f"update_user_main_profile_id 오류: {e}")
            return False, "기본 프로필 ID 업데이트 중 오류가 발생했습니다."


# ==============================================================================
# 4. 초기 실행 (main)
# ==============================================================================

if __name__ == "__main__":
    print("데이터베이스 초기화를 시작합니다...")
    # psycopg2.extras.DictCursor를 사용하기 위해 필요
    try:
        import psycopg2.extras
    except ImportError:
        pass
    initialize_db()
    print("데이터베이스 초기화 완료.")
