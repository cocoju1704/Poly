"""
워크플로우: 링크 수집 → 크롤링 및 구조화

1. crawler/link_collector.py로 보건소 사이트의 모든 서브 메뉴 링크 수집
2. 수집된 각 링크를 crawler/llm_structured_crawler.py로 크롤링하여 구조화
3. 모든 결과를 JSON 파일로 저장
"""

import json
import os
import sys
from datetime import datetime
from typing import List, Dict
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import uuid

# crawler 폴더의 모듈 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "crawler"))
from llm_structured_crawler import LLMStructuredCrawler


class HealthCareWorkflow:
    """보건소 사이트 크롤링 및 구조화 워크플로우"""

    def __init__(self, output_dir: str = "output", region: str = None):
        """
        Args:
            output_dir: 결과 저장 디렉토리
            region: 지역명 (예: "동작구"). None이면 URL에서 자동 추출 시도
        """
        self.output_dir = output_dir
        self.region = region
        self.crawler = LLMStructuredCrawler(model="gpt-4o-mini")

        # 출력 디렉토리 생성
        os.makedirs(output_dir, exist_ok=True)

    def extract_region_from_url(self, url: str) -> str:
        """
        URL에서 지역명 추출 시도

        Args:
            url: 소스 URL

        Returns:
            추출된 지역명 (추출 실패 시 도메인명)
        """
        # 지역 도메인 매핑 (확장 가능)
        region_mapping = {
            "dongjak": "동작구",
            "gangnam": "강남구",
            "seocho": "서초구",
            "songpa": "송파구",
            # 필요에 따라 추가
        }

        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        for key, value in region_mapping.items():
            if key in domain:
                return value

        # 매핑에 없으면 도메인의 첫 부분 반환
        return domain.split(".")[0]

    def collect_links(self, start_url: str, crawl_rules: List[Dict]) -> List[Dict]:
        """
        link_collector.py의 로직을 사용하여 링크 수집

        Args:
            start_url: 시작 URL
            crawl_rules: 크롤링 규칙 리스트

        Returns:
            수집된 링크 리스트 [{'name': '...', 'url': '...'}]
        """
        # base_url 생성
        parsed_url = urlparse(start_url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        # 시작 페이지 파싱
        response = session.get(start_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        # 규칙 찾기
        main_links = []
        active_rule = None

        for rule in crawl_rules:
            main_links = soup.select(rule["main_selector"])
            if main_links:
                print(
                    f"  ✓ 규칙 적용: '{rule['name']}' ({len(main_links)}개 링크 발견)"
                )
                active_rule = rule
                break

        if not active_rule:
            raise ValueError("적용 가능한 크롤링 규칙을 찾을 수 없습니다.")

        # 1단계 메뉴 링크 처리
        main_categories = []
        for link in main_links:
            category_name = link.get_text().strip()
            relative_href = link.get("href")
            absolute_url = urljoin(base_url, relative_href)

            if relative_href.startswith("http"):
                absolute_url = relative_href

            main_categories.append({"name": category_name, "url": absolute_url})

        # 2단계: 각 카테고리의 하위 메뉴 수집
        all_links = []

        for category in main_categories:
            print(f"\n  방문: {category['name']}")

            # 외부 링크 건너뛰기
            if not category["url"].startswith(base_url):
                print("    → 외부 링크, 건너뜀")
                continue

            try:
                category_response = session.get(
                    category["url"], headers=headers, timeout=10
                )
                category_soup = BeautifulSoup(category_response.text, "html.parser")

                # 하위 메뉴 찾기
                sub_links = category_soup.select(active_rule["sub_selector"])

                if sub_links:
                    print(f"    → 하위 메뉴 {len(sub_links)}개 발견")
                    for sub_link in sub_links:
                        sub_name = sub_link.get_text().strip()
                        sub_href = urljoin(base_url, sub_link.get("href"))
                        all_links.append({"name": sub_name, "url": sub_href})
                else:
                    # 하위 메뉴 없으면 카테고리 자체 추가
                    print("    → 하위 메뉴 없음, 카테고리 자체 추가")
                    all_links.append({"name": category["name"], "url": category["url"]})

            except Exception as e:
                print(f"    ✗ 오류: {e}")
                continue

        return all_links

    def run(
        self,
        start_url: str,
        crawl_rules: List[Dict] = None,
        save_links: bool = True,
    ) -> Dict:
        """
        전체 워크플로우 실행

        Args:
            start_url: 시작 URL (보건소 보건사업 페이지)
            crawl_rules: 크롤링 규칙 리스트
            save_links: 수집한 링크를 JSON으로 저장할지 여부

        Returns:
            워크플로우 실행 결과 요약
        """
        print("=" * 80)
        print("보건소 사이트 크롤링 워크플로우 시작")
        print("=" * 80)

        # 기본 크롤링 규칙
        if crawl_rules is None:
            crawl_rules = [
                {
                    "name": "동작구 건강관리청 LNB",
                    "main_selector": ".left-area .left-mdp1 > li > a",
                    "sub_selector": ".left-mdp1 > li.on > ul > li > a",
                },
            ]

        # 1단계: 링크 수집
        print("\n[1단계] 링크 수집 중...")
        print("-" * 80)

        links = self.collect_links(start_url, crawl_rules)

        print(f"\n✅ 총 {len(links)}개의 링크 수집 완료")

        # 링크 저장
        if save_links:
            links_file = os.path.join(self.output_dir, "collected_links.json")
            with open(links_file, "w", encoding="utf-8") as f:
                json.dump(links, f, ensure_ascii=False, indent=2)
            print(f"📄 링크 목록 저장: {links_file}")

        # 2단계: 각 링크 크롤링 및 구조화
        print("\n[2단계] 각 페이지 크롤링 및 LLM 구조화 중...")
        print("-" * 80)

        structured_data_list = []
        failed_urls = []

        for idx, link_info in enumerate(links, 1):
            url = link_info["url"]
            name = link_info["name"]

            print(f"\n[{idx}/{len(links)}] 처리 중: {name}")
            print(f"  URL: {url}")

            try:
                # 크롤링 및 구조화
                structured_data = self.crawler.crawl_and_structure(url=url)

                # 제목이 비어있으면 링크 이름으로 설정
                if not structured_data.title or structured_data.title.strip() == "":
                    structured_data.title = name

                # 최종 JSON 구조로 변환
                final_data = {
                    "id": str(uuid.uuid4()),  # 고유 ID 자동 생성
                    "title": structured_data.title,
                    "support_target": structured_data.eligibility,  # eligibility → support_target
                    "support_content": structured_data.support,  # support → support_content
                    "raw_text": structured_data.raw_text,
                    "source_url": url,
                    "region": self.region
                    or self.extract_region_from_url(url),  # 지역명
                }

                structured_data_list.append(final_data)
                print("  ✅ 성공")

            except Exception as e:
                print(f"  ❌ 실패: {e}")
                failed_urls.append({"url": url, "name": name, "error": str(e)})

        # 3단계: 결과 저장
        print("\n[3단계] 결과 저장 중...")
        print("-" * 80)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 전체 구조화 데이터 저장
        output_file = os.path.join(self.output_dir, f"structured_data_{timestamp}.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(structured_data_list, f, ensure_ascii=False, indent=2)
        print(f"✅ 구조화 데이터 저장: {output_file}")

        # 실패한 URL 저장
        if failed_urls:
            failed_file = os.path.join(self.output_dir, f"failed_urls_{timestamp}.json")
            with open(failed_file, "w", encoding="utf-8") as f:
                json.dump(failed_urls, f, ensure_ascii=False, indent=2)
            print(f"⚠️  실패한 URL 저장: {failed_file}")

        # 요약 정보
        summary = {
            "timestamp": timestamp,
            "start_url": start_url,
            "total_links": len(links),
            "successful": len(structured_data_list),
            "failed": len(failed_urls),
            "output_file": output_file,
        }

        summary_file = os.path.join(self.output_dir, f"summary_{timestamp}.json")
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        # 최종 요약 출력
        print("\n" + "=" * 80)
        print("워크플로우 완료")
        print("=" * 80)
        print(f"📊 총 링크 수: {len(links)}")
        print(f"✅ 성공: {len(structured_data_list)}개")
        print(f"❌ 실패: {len(failed_urls)}개")
        print(f"📁 결과 저장 위치: {self.output_dir}")
        print("=" * 80)

        return summary


def main():
    """메인 실행 함수"""
    import argparse

    parser = argparse.ArgumentParser(
        description="보건소 사이트 크롤링 및 구조화 워크플로우"
    )
    parser.add_argument("--url", type=str, help="시작 URL (보건소 보건사업 페이지)")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="결과 저장 디렉토리 (기본값: output)",
    )
    parser.add_argument(
        "--region",
        type=str,
        default=None,
        help="지역명 (예: 동작구). 지정하지 않으면 URL에서 자동 추출",
    )

    args = parser.parse_args()

    # 대화형 모드
    if not args.url:
        print("\n" + "=" * 80)
        print("보건소 사이트 크롤링 워크플로우")
        print("=" * 80)

        url = input("\n시작 URL을 입력하세요: ").strip()
        if not url:
            print("❌ URL을 입력하지 않았습니다.")
            return

        # 출력 디렉토리
        output_dir_input = input("결과 저장 디렉토리 (Enter: output): ").strip()
        output_dir = output_dir_input if output_dir_input else "output"

        # 지역명
        region_input = input("지역명 (Enter: URL에서 자동 추출): ").strip()
        region = region_input if region_input else None

    else:
        url = args.url
        output_dir = args.output_dir
        region = args.region

    # 워크플로우 실행
    workflow = HealthCareWorkflow(output_dir=output_dir, region=region)

    try:
        summary = workflow.run(start_url=url)
        print("\n✅ 워크플로우 성공적으로 완료!")

    except Exception as e:
        print(f"\n❌ 워크플로우 실패: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
