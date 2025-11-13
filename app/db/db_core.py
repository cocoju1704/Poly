"""11.12 데이터베이스 핵심 연결 기능"""

import psycopg2
import logging
from .config import DB_CONFIG

logger = logging.getLogger(__name__)


def get_db_connection():
    """PostgreSQL DB 연결 객체를 반환합니다."""
    try:
        conn = psycopg2.connect(
            **DB_CONFIG,
            client_encoding="UTF8",  # 한글 처리를 위한 인코딩 설정
        )
        return conn
    except Exception as e:
        logger.error(f"데이터베이스 연결 오류: {e}")
        return None
