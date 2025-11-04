import requests
from bs4 import BeautifulSoup
import json
from typing import Optional
from openai import OpenAI
from pydantic import BaseModel, Field
import os
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()


# Pydantic 모델 정의 - 표준 스키마 (agent.py와 동일한 3필드 구조)
class HealthSupportInfo(BaseModel):
    """건강 지원 정보 표준 스키마"""

    title: str = Field(description="공고/사업/프로그램의 제목(한 줄)")
    eligibility: str = Field(description="지원 대상 또는 신청/참가 자격을 간결히 요약")
    support: str = Field(description="지원 내용/혜택/지원 항목을 핵심만 요약")
    raw_text: Optional[str] = Field(
        default=None, description="원본 텍스트 - 구조화 전 크롤링한 원본 데이터"
    )


# LLM 응답용 내부 모델 (raw_text 제외)
class _HealthSupportInfoResponse(BaseModel):
    """LLM 응답용 내부 모델 - raw_text 제외"""

    title: str = Field(description="공고/사업/프로그램의 제목(한 줄)")
    eligibility: str = Field(description="지원 대상 또는 신청/참가 자격을 간결히 요약")
    support: str = Field(description="지원 내용/혜택/지원 항목을 핵심만 요약")


class LLMStructuredCrawler:
    """LLM을 사용하여 크롤링 데이터를 구조화하는 크롤러"""

    def __init__(self, api_key: str = None, model: str = "gpt-4o"):
        """
        Args:
            api_key: OpenAI API 키 (없으면 환경변수에서 가져옴)
            model: 사용할 모델 (gpt-4o, gpt-4o-mini 등)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API 키가 필요합니다. 환경변수 OPENAI_API_KEY를 설정하거나 api_key 파라미터를 전달하세요."
            )

        self.client = OpenAI(api_key=self.api_key)
        self.model = model

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

    def fetch_page(self, url: str) -> BeautifulSoup:
        """웹페이지 가져오기"""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            response.encoding = "utf-8"
            return BeautifulSoup(response.text, "html.parser")
        except requests.RequestException as e:
            print(f"페이지 요청 실패: {e}")
            return None

    def parse_html_file(self, file_path: str) -> BeautifulSoup:
        """로컬 HTML 파일 파싱"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                html_content = f.read()
            return BeautifulSoup(html_content, "html.parser")
        except Exception as e:
            print(f"파일 읽기 실패: {e}")
            return None

    def extract_text_content(self, soup: BeautifulSoup) -> str:
        """HTML에서 주요 텍스트 내용 추출"""
        # contentArea 또는 content 영역 찾기
        content_area = (
            soup.select_one("#contentArea")
            or soup.select_one("#content")
            or soup.select_one("#contentDiv")
        )

        if not content_area:
            content_area = soup

        # 불필요한 요소 제거
        for element in content_area.select("script, style, .share_box, .research"):
            element.decompose()

        # 텍스트 추출
        text = content_area.get_text(separator="\n", strip=True)

        # 빈 줄 제거 및 정리
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        cleaned_text = "\n".join(lines)

        return cleaned_text

    def structure_with_llm(
        self, raw_text: str, use_structured_output: bool = True
    ) -> HealthSupportInfo:
        """
        LLM을 사용하여 텍스트를 구조화

        Args:
            raw_text: 크롤링한 원본 텍스트
            use_structured_output: OpenAI Structured Output 사용 여부
        """
        system_prompt = """너는 한국어 공고문을 구조적으로 요약하는 보조자야.
다음 원문에서 '제목', '지원 대상(자격)', '지원 내용'을 꼭 뽑아.
규칙:
- 원문에 근거해 작성하고, 없으면 '원문에 정보가 부족합니다'라고 적어.
- 제목은 한 줄로 요약.
- 지원 대상과 지원 내용은 핵심만 요약 (길어도 4~6줄 이내).
- 포맷은 제공된 JSON 스키마에 맞춰 반환."""

        user_prompt = f"""다음 원문에서 정보를 추출해줘:

================ RAW TEXT ================
{raw_text}
========================================="""

        try:
            if use_structured_output:
                # Structured Output 사용 (더 정확함) - 내부 응답 모델 사용
                completion = self.client.beta.chat.completions.parse(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format=_HealthSupportInfoResponse,
                    temperature=0.1,
                )

                # 응답을 HealthSupportInfo로 변환하면서 raw_text 추가
                response_data = completion.choices[0].message.parsed
                return HealthSupportInfo(
                    **response_data.model_dump(), raw_text=raw_text
                )

            else:
                # 일반 JSON 모드 사용
                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                )

                result_json = json.loads(completion.choices[0].message.content)
                return HealthSupportInfo(**result_json, raw_text=raw_text)

        except Exception as e:
            print(f"LLM 구조화 실패: {e}")
            raise

    def crawl_and_structure(
        self, url: str = None, file_path: str = None
    ) -> HealthSupportInfo:
        """
        웹페이지 또는 파일을 크롤링하고 LLM으로 구조화

        Args:
            url: 크롤링할 URL
            file_path: 로컬 HTML 파일 경로

        Returns:
            구조화된 HealthSupportInfo 객체
        """
        # 1. HTML 가져오기
        if url:
            soup = self.fetch_page(url)
        elif file_path:
            soup = self.parse_html_file(file_path)
        else:
            raise ValueError("url 또는 file_path 중 하나는 필수입니다.")

        if not soup:
            raise ValueError("HTML을 가져올 수 없습니다.")

        # 2. 텍스트 추출
        raw_text = self.extract_text_content(soup)

        # 3. LLM으로 구조화
        structured_data = self.structure_with_llm(raw_text)

        return structured_data

    def save_to_json(self, data: HealthSupportInfo, output_path: str):
        """구조화된 데이터를 JSON으로 저장"""
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data.model_dump(), f, ensure_ascii=False, indent=2)
            print(f"[OK] 데이터가 {output_path}에 저장되었습니다.")
        except Exception as e:
            print(f"[ERROR] 파일 저장 실패: {e}")

    def print_structured_data(self, data: HealthSupportInfo):
        """구조화된 데이터를 보기 좋게 출력"""
        print("\n" + "=" * 80)
        print(f"■ 제목\n{data.title}")
        print("=" * 80)

        if data.eligibility:
            print("\n■ 지원 대상(자격)")
            self._print_multiline(data.eligibility, indent=1)

        if data.support:
            print("\n■ 지원 내용")
            self._print_multiline(data.support, indent=1)

        print("\n" + "=" * 80)

    def _print_multiline(self, text: str, indent: int = 0):
        """여러 줄 텍스트를 들여쓰기하여 출력"""
        prefix = "  " * indent
        lines = text.split("\n")
        for line in lines:
            if line.strip():
                print(f"{prefix}{line.strip()}")


def main():
    """메인 실행 함수"""
    import argparse

    parser = argparse.ArgumentParser(
        description="LLM을 사용하여 의료비 지원 정보를 크롤링하고 구조화합니다."
    )
    parser.add_argument("--url", type=str, help="크롤링할 웹페이지 URL")
    parser.add_argument("--file", type=str, help="크롤링할 로컬 HTML 파일 경로")
    parser.add_argument(
        "--output",
        type=str,
        default="structured_output.json",
        help="출력 JSON 파일 경로",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o-mini",
        help="사용할 OpenAI 모델 (기본값: gpt-4o-mini)",
    )

    args = parser.parse_args()

    # URL 또는 파일 경로가 없으면 대화형 모드
    if not args.url and not args.file:
        print("\n" + "=" * 80)
        print("LLM 기반 의료비 지원 정보 크롤러")
        print("=" * 80)
        print("\n옵션을 선택하세요:")

        args.url = input("웹페이지 URL을 입력하세요: ").strip()
        args.output = (
            input("출력 파일명 (기본값: structured_output.json): ").strip()
            or "structured_output.json"
        )

    # LLM 크롤러 생성
    crawler = LLMStructuredCrawler(model=args.model)

    print(f"\n{'=' * 80}")
    if args.url:
        print(f"처리 중: {args.url}")
    else:
        print(f"처리 중: {args.file}")
    print(f"{'=' * 80}")

    try:
        # 크롤링 및 구조화
        if args.url:
            structured_data = crawler.crawl_and_structure(url=args.url)
        else:
            structured_data = crawler.crawl_and_structure(file_path=args.file)

        # 결과 출력
        crawler.print_structured_data(structured_data)

        # JSON 저장
        crawler.save_to_json(structured_data, args.output)

        print(f"\n[완료] 구조화된 데이터가 {args.output}에 저장되었습니다.")

    except Exception as e:
        print(f"[ERROR] 처리 실패: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
