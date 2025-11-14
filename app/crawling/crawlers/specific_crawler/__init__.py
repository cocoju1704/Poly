"""
특정 구별 크롤러 모듈
"""

from .district_menu_crawler import DistrictMenuCrawler
from .songpa_crawler import SongpaCrawler
from .yangcheon_crawler import YangcheonCrawler
from .ehealth_crawler import EHealthCrawler
from .welfare_crawler import WelfareCrawler
from . import district_configs

__all__ = [
    "DistrictMenuCrawler",
    "SongpaCrawler",
    "YangcheonCrawler",
    "EHealthCrawler",
    "WelfareCrawler",
    "district_configs",
]
