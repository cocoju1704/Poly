"""
통합 헬스케어 챗봇: 워크플로우 + Agentic RAG

1. workflow.py 기능: 웹사이트에서 건강 지원 정보 수집 및 구조화
2. agent.py 기능: FAISS 벡터 스토어 + 검색 도구 + 멀티턴 대화
3. PDF 로더: PyMuPDF를 사용한 PDF 파일 처리
"""

import json
import os
import sys
import asyncio
from typing import List, Dict
from datetime import datetime

from workflow import HealthCareWorkflow

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langchain_community.vectorstores import FAISS
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain_core.documents import Document

# crawler 폴더 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "crawler"))


# 환경 변수 로드
load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
TEMP = float(os.getenv("TEMPERATURE", "0.2"))


class HealthCareChatbot:
    """통합 헬스케어 챗봇 - 데이터 수집 + RAG 검색 + 대화"""

    def __init__(
        self, output_dir: str = "output", data_file: str = None, region: str = None,
        chunk_strategy: str = "per_item"
    ):
        """
        Args:
            output_dir: 데이터 저장 디렉토리
            data_file: 기존 JSON 파일 경로 (있으면 재사용)
            region: 지역명 (데이터 수집 시 사용)
        """
        self.output_dir = output_dir
        self.data_file = data_file
        self.region = region
        self.structured_data = []
        self.vector_store = None
        self.agent_executor = None
        self.conversation_region = None  # 대화 시 사용할 지역명

        # 디렉토리 생성
        os.makedirs(output_dir, exist_ok=True)
        # FAISS 저장 경로
        self.faiss_dir = os.path.join(self.output_dir, "faiss_index")
        # 임베딩 모델명 공유 (저장/로드 시 동일해야 함)
        self.embedding_model_name = 'text-embedding-3-large'
        # 청킹 전략: per_item | by_fields | split
        self.chunk_strategy = chunk_strategy

    def collect_data(
        self,
        start_url: str,
        crawl_rules: List[Dict] = None,
        force_recollect: bool = False,
    ) -> str:
        """
        웹사이트에서 데이터 수집 (workflow.py 기능)

        Args:
            start_url: 시작 URL
            crawl_rules: 크롤링 규칙
            force_recollect: True면 기존 데이터 무시하고 재수집

        Returns:
            생성된 JSON 파일 경로
        """
        # 기존 파일이 있고 재수집 안 하면 건너뛰기
        if self.data_file and os.path.exists(self.data_file) and not force_recollect:
            print(f"✓ 기존 데이터 사용: {self.data_file}")
            return self.data_file

        print("\n" + "=" * 80)
        print("🔍 데이터 수집 시작 (workflow)")
        print("=" * 80)

        # workflow 실행
        workflow = HealthCareWorkflow(output_dir=self.output_dir, region=self.region)

        summary = workflow.run(start_url=start_url, crawl_rules=crawl_rules)

        self.data_file = summary["output_file"]
        print(f"\n✅ 데이터 수집 완료: {self.data_file}")

        return self.data_file


    def load_data(self, data_file: str = None) -> List[Dict]:
        """
        JSON 파일에서 데이터 로드

        Args:
            data_file: JSON 파일 경로 (None이면 self.data_file 사용)

        Returns:
            구조화된 데이터 리스트
        """
        file_path = data_file or self.data_file

        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(
                f"데이터 파일을 찾을 수 없습니다: {file_path}\n"
                "먼저 collect_data() 또는 load_pdf()를 실행하여 데이터를 수집하세요."
            )

        print(f"\n📂 데이터 로드 중: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            self.structured_data = json.load(f)

        print(f"✅ {len(self.structured_data)}개 문서 로드 완료")

        return self.structured_data

    def build_vector_store(self) -> FAISS:
        """
        FAISS 벡터 스토어 구축 (agent.py 기능)

        Returns:
            FAISS 벡터 스토어
        """
        if not self.structured_data:
            raise ValueError("데이터가 없습니다. 먼저 load_data()를 실행하세요.")

        print("\n" + "=" * 80)
        print("🧠 벡터 스토어 구축 중...")
        print("=" * 80)

        # 문서 생성
        documents = []
        for item in self.structured_data:
            raw_text = item.get("raw_text", "")
            if not raw_text:
                continue

            # 메타데이터 포함
            metadata = {
                "id": item.get("id", ""),
                "title": item.get("title", ""),
                "source_url": item.get("source_url", ""),
                "region": item.get("region", ""),
                "support_target": item.get("support_target", ""),
                "support_content": item.get("support_content", ""),
            }
            # PDF 페이지 정보가 있으면 추가
            if "page_number" in item:
                metadata["page_number"] = item.get("page_number")
                metadata["total_pages"] = item.get("total_pages")

            doc = Document(page_content=raw_text, metadata=metadata)
            documents.append(doc)

        print(f"  → {len(documents)}개 문서 준비 완료")

        
        # 길이 기반 분할
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=700, chunk_overlap=100, separators=["\n\n", "\n", " ", ""]
        )
        chunks = splitter.split_documents(documents)
        print(f"  → {len(chunks)}개 청크로 분할 완료(split)")

        # 임베딩 및 벡터 스토어 생성
        print("  → 임베딩 모델 로딩 중...")
        
        # OpenAI 임베딩 모델 사용
        embeddings = OpenAIEmbeddings(model=self.embedding_model_name)
        
        self.vector_store = FAISS.from_documents(chunks, embeddings)
        # 로컬 저장
        os.makedirs(self.faiss_dir, exist_ok=True)
        self.vector_store.save_local(self.faiss_dir)

        print(f"✅ 벡터 스토어 구축 완료 (저장 위치: {self.faiss_dir})\n")

        return self.vector_store

    def load_vector_store(self) -> FAISS:
        """
        로컬에 저장된 FAISS 벡터 스토어 로드

        Returns:
            FAISS 벡터 스토어 (성공 시), 없으면 None
        """
        # 저장 파일 존재 확인 (기본 파일: index.faiss, index.pkl)
        if not os.path.isdir(self.faiss_dir):
            return None
        index_faiss = os.path.join(self.faiss_dir, "index.faiss")
        index_pkl = os.path.join(self.faiss_dir, "index.pkl")
        if not (os.path.exists(index_faiss) and os.path.exists(index_pkl)):
            return None

        print("\n" + "=" * 80)
        print("📦 로컬 벡터 스토어 로드 중...")
        print("=" * 80)

        embeddings = OpenAIEmbeddings(model=self.embedding_model_name)

        try:
            # allow_dangerous_deserialization 은 최신 버전에서 필요할 수 있음
            self.vector_store = FAISS.load_local(
                self.faiss_dir, embeddings, allow_dangerous_deserialization=True
            )
            print("✅ 로컬 벡터 스토어 로드 완료\n")
            return self.vector_store
        except Exception as e:
            print(f"⚠️  로컬 벡터 스토어 로드 실패: {e}")
            return None

    def setup_agent(self):
        """
        LangChain 에이전트 설정 (agent.py 기능)
        """
        if not self.vector_store:
            raise ValueError(
                "벡터 스토어가 없습니다. 먼저 build_vector_store()를 실행하세요."
            )

        print("🤖 에이전트 설정 중...")

        @tool
        def search_with_score(query: str) -> str:
            """
            건강 지원 정보 데이터베이스에서 유사도 점수와 함께 검색합니다.
            """
            try:
                results = self.vector_store.similarity_search_with_score(
                    query, 
                    k=7
                )

                if not results:
                    return "검색 결과가 없습니다."

                out = []
                for i, (doc, score) in enumerate(results, start=1):
                    meta = doc.metadata
                    preview = doc.page_content[:200].replace("\n", " ")

                    out.append(
                        f"[문서 {i} | 점수: {score:.4f}]\n"
                        f"제목: {meta.get('title', 'N/A')}\n"
                        f"지역: {meta.get('region', 'N/A')}\n"
                        f"내용: {preview}...\n"
                        f"URL: {meta.get('source_url', 'N/A')}\n"
                    )

                return "\n".join(out)
            except Exception as e:
                return f"검색 중 오류가 발생했습니다: {e}"

        tools = [search_with_score]

        # 프롬프트 설정
        SYSTEM_PROMPT = """당신은 보건소 건강 지원 정보를 안내하는 전문 상담원입니다.

지침:
- 사용자의 질문에 대해 검색 도구를 사용하여 관련 정보를 찾을 것
- 검색 결과를 바탕으로 명확하고 친절하게 답변할 것
- 지원 대상, 지원 내용, 신청 방법 등 핵심 정보를 간결하게 요약할 것
- 여러 지역의 정보가 있다면 지역별로 구분하여 안내해야하며 만약 제공된 문서에 세부 지원 내용이 존재한다면 그 내용을 기반으로 답변할 것
- 정보가 부족하면 "해당 정보를 찾을 수 없습니다"라고 솔직히 답변할 것
- 예시로 질문 : 암 지원에 대해 알려줘 인 경우 제공 문서에 암 지원이 없으면 참조 하지 않을 것
- 답변 끝에는 출처 URL을 제공하세요.
"""

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )

        # LLM 및 에이전트 생성
        llm = ChatOpenAI(model=MODEL, temperature=TEMP, streaming=True)
        agent = create_openai_tools_agent(llm, tools, prompt)

        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=5,
        )

        print("✅ 에이전트 설정 완료\n")

    def print_summary(self):
        """수집된 데이터 요약 출력"""
        if not self.structured_data:
            print("⚠️  로드된 데이터가 없습니다.")
            return

        print("\n" + "=" * 80)
        print("📊 수집된 데이터 요약")
        print("=" * 80)

        # 지역별 통계
        region_count = {}
        for item in self.structured_data:
            region = item.get("region", "미지정")
            region_count[region] = region_count.get(region, 0) + 1

        print(f"\n총 문서 수: {len(self.structured_data)}개")
        print("\n지역별 분포:")
        for region, count in region_count.items():
            print(f"  - {region}: {count}개")

        print("\n최근 문서 3개:")
        for i, item in enumerate(self.structured_data[:3], 1):
            print(f"\n  [{i}] {item.get('title', 'N/A')}")
            print(f"      지역: {item.get('region', 'N/A')}")
            print(f"      URL: {item.get('source_url', 'N/A')}")

        print("\n" + "=" * 80)

    async def run_conversation(self):
        """
        멀티턴 대화 실행 (agent.py 기능)
        """
        if not self.agent_executor:
            raise ValueError(
                "에이전트가 설정되지 않았습니다. 먼저 setup_agent()를 실행하세요."
            )

        chat_history = []

        # 요약 정보 출력
        self.print_summary()

        print("\n" + "=" * 80)
        print("💬 헬스케어 챗봇 (건강 지원 정보 상담)")
        print("=" * 80)
        print("종료: quit/exit/종료 | 초기화: reset/clear/초기화")
        print("=" * 80)

        while True:
            user_input = await asyncio.to_thread(input, "종료를 원하시면 종료/exit/quit 입력\n초기화를 원하시면 초기화/reset/clear 입력\n질문: ")
            if user_input is None:
                continue
            user_input = user_input.strip()

            # 종료 명령
            if user_input.lower() in ["exit", "quit", "종료"]:
                print("\n👋 시스템을 종료합니다.")
                break

            # 초기화 명령
            if user_input.lower() in ["reset", "clear", "초기화"]:
                chat_history = []
                print("\n🔄 대화 내용이 초기화되었습니다.")
                self.print_summary()
                continue

            if not user_input:
                continue

            try:
                print("답변: ", end="", flush=True)
                full_response = ""

                # 스트리밍 응답
                async for event in self.agent_executor.astream_events(
                    {"input": user_input, "chat_history": chat_history},
                    version="v2",
                ):
                    kind = event["event"]

                    if kind == "on_tool_start":
                        tool_name = event["name"]
                        print(f"\n[🔍 {tool_name} 검색 중...]", end="", flush=True)
                        print("\n답변: ", end="", flush=True)

                    elif kind == "on_chat_model_stream":
                        chunk = event["data"]["chunk"].content
                        if chunk:
                            print(chunk, end="", flush=True)
                            full_response += chunk

                print()  # 줄바꿈

                # 대화 기록 업데이트
                chat_history.append(HumanMessage(content=user_input))
                chat_history.append(AIMessage(content=full_response))

            except Exception as e:
                print(f"\n❌ 오류 발생: {e}")

    def initialize(
        self,
        start_url: str = None,
        data_file: str = None,
        pdf_file: str = None,
        crawl_rules: List[Dict] = None,
        force_recollect: bool = False,
    ):
        """
        챗봇 초기화 (전체 파이프라인)

        Args:
            start_url: 데이터 수집할 URL (data_file, pdf_file이 없을 때 필요)
            data_file: 기존 JSON 파일 경로
            pdf_file: PDF 파일 경로
            crawl_rules: 크롤링 규칙
            force_recollect: 강제 재수집 여부
        """
        print("\n" + "=" * 80)
        print("🚀 헬스케어 챗봇 초기화")
        print("=" * 80)

        # 1. 데이터 준비
        if pdf_file:
            print(f"\n[1] PDF 파일 처리: {pdf_file}")
            self.load_pdf(pdf_file, force_recollect)
            # PDF 처리 후 자동으로 데이터가 로드됨 (self.structured_data)
        elif data_file and os.path.exists(data_file):
            print(f"\n[1] 기존 데이터 사용: {data_file}")
            self.data_file = data_file
        elif start_url:
            print(f"\n[1] 웹사이트에서 데이터 수집: {start_url}")
            self.collect_data(start_url, crawl_rules, force_recollect)
        else:
            raise ValueError(
                "start_url, data_file, pdf_file 중 하나는 필수입니다.\n"
                "새로 수집하려면 start_url을, 기존 데이터를 사용하려면 data_file을, "
                "PDF 파일을 처리하려면 pdf_file을 제공하세요."
            )

        # 2. 데이터 로드 (PDF가 아닌 경우만)
        if not pdf_file:
            print("\n[2] 데이터 로드")
            self.load_data()
        else:
            print("\n[2] PDF 데이터 이미 로드됨")

        # 3. 벡터 스토어 로드/구축
        print("\n[3] 벡터 스토어 준비")
        loaded = self.load_vector_store()
        if loaded is None:
            print("로컬 인덱스가 없어 새로 구축합니다.")
            self.build_vector_store()

        # 4. 에이전트 설정
        print("\n[4] 에이전트 설정")
        self.setup_agent()

        print("\n" + "=" * 80)
        print("✅ 초기화 완료! 이제 대화를 시작할 수 있습니다.")
        print("=" * 80)


def main():
    """메인 실행 함수"""
    import argparse

    parser = argparse.ArgumentParser(
        description="통합 헬스케어 챗봇 - 데이터 수집 + RAG + 대화"
    )
    parser.add_argument("--url", type=str, help="데이터 수집할 웹사이트 URL")
    parser.add_argument("--data-file", type=str, help="기존 JSON 데이터 파일 경로")
    parser.add_argument("--pdf-file", type=str, help="PDF 파일 경로 (PyMuPDF 사용)")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="데이터 저장 디렉토리 (기본값: output)",
    )
    parser.add_argument("--region", type=str, help="지역명 (예: 동작구)")
    parser.add_argument(
        "--force-recollect",
        action="store_true",
        help="기존 데이터 무시하고 강제 재수집",
    )
    parser.add_argument(
        "--chunk-strategy",
        type=str,
        choices=["per_item", "by_fields", "split"],
        default="per_item",
        help="청킹 전략 선택 (per_item | by_fields | split)",
    )

    args = parser.parse_args()

    # 대화형 모드
    if not args.url and not args.data_file and not args.pdf_file:
        print("\n" + "=" * 80)
        print("통합 헬스케어 챗봇")
        print("=" * 80)
        print("\n데이터 소스를 선택하세요:")
        print("  1. 웹사이트에서 새로 수집")
        print("  2. 기존 JSON 파일 사용")
        print("  3. PDF 파일 사용 ## 현재 사용 안함 ##")

        choice = input("\n선택 (1, 2, 또는 3): ").strip()

        if choice == "1":
            url = input("웹사이트 URL: ").strip()
            if not url:
                print("❌ URL을 입력하지 않았습니다.")
                return
            region = input("지역명 (Enter: 자동 추출): ").strip() or None
            data_file = None
            pdf_file = None
        elif choice == "2":
            data_file = input("JSON 파일 경로: ").strip()
            if not data_file or not os.path.exists(data_file):
                print(f"❌ 파일을 찾을 수 없습니다: {data_file}")
                return
            url = None
            pdf_file = None
            region = None
        elif choice == "3":
            pdf_file = input("PDF 파일 경로: ").strip()
            if not pdf_file or not os.path.exists(pdf_file):
                print(f"❌ 파일을 찾을 수 없습니다: {pdf_file}")
                return
            url = None
            data_file = None
            region = input("지역명 (Enter: 미지정): ").strip() or None
        else:
            print("❌ 잘못된 선택입니다.")
            return

        output_dir = input("데이터 저장 디렉토리 (Enter: output): ").strip() or "output"

    else:
        url = args.url
        data_file = args.data_file
        pdf_file = args.pdf_file
        output_dir = args.output_dir
        region = args.region

    # 챗봇 생성 및 초기화
    try:
        chatbot = HealthCareChatbot(
            output_dir=output_dir, data_file=data_file, region=region,
            chunk_strategy=getattr(args, "chunk_strategy", "per_item")
        )

        chatbot.initialize(
            start_url=url,
            data_file=data_file,
            pdf_file=pdf_file,
            force_recollect=args.force_recollect
            if hasattr(args, "force_recollect")
            else False,
        )

        # 대화 시작
        asyncio.run(chatbot.run_conversation())

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
