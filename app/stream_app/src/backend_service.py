import time
import logging
from typing import Dict, Any, Tuple, Optional

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock 데이터
MOCK_API_DELAY = 0.5
RESERVED_IDS = ["admin", "root", "system"]
TEST_USER = {"id": "test", "password": "1234"}


def api_check_id_availability(user_id: str) -> Tuple[bool, str]:
    """
    아이디 중복 확인 (Mock)

    Args:
        user_id (str): 확인할 사용자 ID

    Returns:
        Tuple[bool, str]: (사용 가능 여부, 메시지)
    """
    try:
        time.sleep(MOCK_API_DELAY)
        is_available = user_id not in RESERVED_IDS
        message = (
            "사용 가능한 아이디입니다"
            if is_available
            else "이미 사용 중인 아이디입니다"
        )
        logger.info(f"ID 중복 확인: {user_id} - {message}")
        return is_available, message
    except Exception as e:
        logger.error(f"ID 중복 확인 중 오류 발생: {str(e)}")
        return False, "확인 중 오류가 발생했습니다"


def api_login(user_id: str, password: str) -> Tuple[bool, str]:
    """
    로그인 (Mock)

    Args:
        user_id (str): 사용자 ID
        password (str): 비밀번호

    Returns:
        Tuple[bool, str]: (로그인 성공 여부, 메시지)
    """
    try:
        time.sleep(MOCK_API_DELAY)
        is_valid = user_id == TEST_USER["id"] and password == TEST_USER["password"]
        message = (
            "로그인 성공" if is_valid else "아이디 또는 비밀번호가 일치하지 않습니다"
        )
        logger.info(f"로그인 시도: {user_id} - {'성공' if is_valid else '실패'}")
        return is_valid, message
    except Exception as e:
        logger.error(f"로그인 중 오류 발생: {str(e)}")
        return False, "로그인 처리 중 오류가 발생했습니다"


def api_signup(user_id: str, profile_data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    회원가입 (Mock)

    Args:
        user_id (str): 사용자 ID
        profile_data (Dict[str, Any]): 프로필 데이터

    Returns:
        Tuple[bool, str]: (가입 성공 여부, 메시지)
    """
    try:
        time.sleep(MOCK_API_DELAY)
        # 실제 구현에서는 DB 저장 로직 필요
        logger.info(f"회원가입 성공: {user_id}")
        logger.debug(f"프로필 데이터: {profile_data}")
        return True, "회원가입이 완료되었습니다"
    except Exception as e:
        logger.error(f"회원가입 중 오류 발생: {str(e)}")
        return False, "회원가입 처리 중 오류가 발생했습니다"


def api_send_chat_message(
    message: str, user_profile: Optional[Dict] = None
) -> Tuple[bool, Dict]:
    """
    챗봇 메시지 전송 (Mock)

    Args:
        message (str): 사용자 메시지
        user_profile (Dict): 사용자 프로필 정보

    Returns:
        Tuple[bool, Dict]: (성공 여부, 응답 데이터)
    """
    try:
        time.sleep(MOCK_API_DELAY)
        return True, {
            "content": "고객님의 조건에 맞는 정책을 찾았습니다.",
            "policies": [
                {
                    "id": "1",
                    "title": "청년 월세 지원",
                    "description": "만 19세~34세 청년의 주거비 부담을 덜어주기 위한 월세 지원 정책입니다.",
                    "eligibility": "만 19~34세, 소득 기준 충족, 서울시 거주",
                    "benefits": "월 최대 20만원 지원 (최대 12개월)",
                    "applicationUrl": "https://example.com/apply",
                    "isEligible": True,
                }
            ],
        }
    except Exception as e:
        logger.error(f"메시지 전송 중 오류 발생: {str(e)}")
        return False, {"error": "메시지 전송 중 오류가 발생했습니다"}


def api_get_chat_history(limit: int = 10) -> Tuple[bool, list]:
    """
    채팅 내역 조회 (Mock)

    Args:
        limit (int): 조회할 내역 수

    Returns:
        Tuple[bool, list]: (성공 여부, 채팅 내역 리스트)
    """
    try:
        time.sleep(MOCK_API_DELAY)
        return True, []
    except Exception as e:
        logger.error(f"채팅 내역 조회 중 오류 발생: {str(e)}")
        return False, []


def api_update_profile(profile_data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    프로필 업데이트 (Mock)

    Args:
        profile_data (Dict[str, Any]): 업데이트할 프로필 데이터

    Returns:
        Tuple[bool, str]: (성공 여부, 메시지)
    """
    try:
        time.sleep(MOCK_API_DELAY)
        return True, "프로필이 업데이트되었습니다"
    except Exception as e:
        logger.error(f"프로필 업데이트 중 오류 발생: {str(e)}")
        return False, "프로필 업데이트 중 오류가 발생했습니다"


def api_reset_password(current_password: str, new_password: str) -> Tuple[bool, str]:
    """
    비밀번호 재설정 (Mock)

    Args:
        current_password (str): 현재 비밀번호
        new_password (str): 새 비밀번호

    Returns:
        Tuple[bool, str]: (성공 여부, 메시지)
    """
    try:
        time.sleep(MOCK_API_DELAY)
        return True, "비밀번호가 변경되었습니다"
    except Exception as e:
        logger.error(f"비밀번호 재설정 중 오류 발생: {str(e)}")
        return False, "비밀번호 변경 중 오류가 발생했습니다"


def api_delete_account() -> Tuple[bool, str]:
    """
    회원 탈퇴 (Mock)

    Returns:
        Tuple[bool, str]: (성공 여부, 메시지)
    """
    try:
        time.sleep(MOCK_API_DELAY)
        return True, "회원 탈퇴가 완료되었습니다"
    except Exception as e:
        logger.error(f"회원 탈퇴 중 오류 발생: {str(e)}")
        return False, "회원 탈퇴 처리 중 오류가 발생했습니다"
