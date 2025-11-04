# -*- coding: utf-8 -*-
import os
import asyncio
from typing import Optional
from dotenv import load_dotenv

from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langchain_community.vectorstores import FAISS
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain_core.documents import Document

# =========================
# 0) 환경 설정
# =========================
load_dotenv()
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
TEMP = float(os.getenv("TEMPERATURE", "0.2"))

RAW_PATH = "rawtext.txt"
if not os.path.exists(RAW_PATH):
    raise FileNotFoundError("프로젝트 루트에 rawtext.txt가 필요합니다.")

with open(RAW_PATH, "r", encoding="utf-8") as f:
    raw_text = f.read()


# =========================
# 1) LLM 기반 구조화 추출
# =========================
class NoticeInfo(BaseModel):
    """공고문에서 반드시 추출해야 하는 필드 정의"""

    title: str = Field(description="공고/사업/프로그램의 제목(한 줄)")
    eligibility: str = Field(description="지원 대상 또는 신청/참가 자격을 간결히 요약")
    support: str = Field(description="지원 내용/혜택/지원 항목을 핵심만 요약")
    confidence: Optional[float] = Field(
        default=None, description="추출 신뢰도(0~1). 확신이 없으면 0.4 이하로 설정"
    )


def extract_structured_info_llm(text: str) -> NoticeInfo:
    """
    LLM이 rawtext에서 필수 필드를 구조화하여 반환.
    - LangChain structured output(Pydantic)을 사용해 JSON 스키마로 강제.
    - 내용이 부족하면 '원문에 정보가 부족합니다'라고 채우도록 지시.
    """
    extractor_llm = ChatOpenAI(model=MODEL, temperature=0)  # 추출은 결정적이게
    structured = extractor_llm.with_structured_output(NoticeInfo)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """너는 한국어 공고문을 구조적으로 요약하는 보조자야.
다음 원문에서 '제목', '지원 대상(자격)', '지원 내용'을 꼭 뽑아.
규칙:
- 원문에 근거해 작성하고, 없으면 '원문에 정보가 부족합니다'라고 적어.
- 제목은 한 줄로 요약.
- 지원 대상과 지원 내용은 핵심만 요약 (길어도 4~6줄 이내).
- 포맷은 제공된 JSON 스키마(NoticeInfo)에 맞춰 반환.""",
            ),
            (
                "human",
                "다음 원문에서 정보를 추출해줘:\n\n================ RAW TEXT ================\n{raw}\n=========================================",
            ),
        ]
    )

    chain = prompt | structured
    return chain.invoke({"raw": text})


extracted = extract_structured_info_llm(raw_text)

# =========================
# 2) 인덱싱(인메모리 FAISS)
# =========================
splitter = RecursiveCharacterTextSplitter(
    chunk_size=800, chunk_overlap=120, separators=["\n\n", "\n", " ", ""]
)
docs = [Document(page_content=raw_text, metadata={"source": "rawtext.txt"})]
chunks = splitter.split_documents(docs)

embeddings = OpenAIEmbeddings()  # text-embedding-3-small 기본
vector_store = FAISS.from_documents(chunks, embeddings)


# =========================
# 3) 검색 도구 (@tool)
# =========================
@tool
def search_documents(query: str) -> str:
    """
    인메모리 FAISS에서 유사 문서를 검색하여 본문을 반환합니다.
    """
    try:
        results = vector_store.similarity_search(query, k=5)
        if not results:
            return "검색 결과가 없습니다."
        out = []
        for i, doc in enumerate(results, start=1):
            out.append(
                f"[문서 {i} | 출처: {doc.metadata.get('source', 'rawtext.txt')}]\n{doc.page_content}\n"
            )
        return "\n".join(out)
    except Exception as e:
        return f"검색 중 오류가 발생했습니다: {e}"


@tool
def search_documents_with_score(query: str) -> str:
    """
    인메모리 FAISS에서 유사 문서를 검색하여 유사도 점수와 함께 반환합니다.
    """
    try:
        results = vector_store.similarity_search_with_score(query, k=5)
        if not results:
            return "검색 결과가 없습니다."
        out = []
        for i, (doc, score) in enumerate(results, start=1):
            preview = doc.page_content[:500].replace("\n", " ")
            out.append(
                f"[문서 {i} | 점수: {score:.4f} | 출처: {doc.metadata.get('source', 'rawtext.txt')}] {preview}..."
            )
        return "\n".join(out)
    except Exception as e:
        return f"검색 중 오류가 발생했습니다: {e}"


tools = [search_documents, search_documents_with_score]

# =========================
# 4) 프롬프트 & 에이전트
# =========================
SYSTEM_PROMPT = """당신은 사용자가 제공한 rawtext.txt만을 근거로 답하는 한국어 분석가입니다.

지침:
- 반드시 제공된 검색 결과(툴 출력) 범위 안에서만 답하세요.
- 근거가 부족하면 '원문에 정보가 부족합니다'라고 명시하세요.
- 핵심 요점을 짧게 bullet로 정리해도 좋습니다.
- 답변 끝에 간단히 출처를 표기하세요. (예: 출처: rawtext.txt)
"""

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ]
)

llm = ChatOpenAI(model=MODEL, temperature=TEMP, streaming=True)
agent = create_openai_tools_agent(llm, tools, prompt)

agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    handle_parsing_errors=True,
    max_iterations=5,
)


# =========================
# 5) 멀티턴 + 스트리밍 루프
# =========================
def print_pre_extracted_info_llm(n: NoticeInfo) -> None:
    print("=" * 70)
    print("🤖 LLM 사전 추출 정보 (rawtext 기반)")
    print("=" * 70)
    print(f"■ 제목\n{n.title}\n")
    print(f"■ 지원 대상(자격)\n{n.eligibility}\n")
    print(f"■ 지원 내용\n{n.support}\n")
    if n.confidence is not None:
        print(f"■ 신뢰도(LLM 자체 추정): {n.confidence:.2f}\n")
    print("-" * 70)


async def run_multiturn_conversation():
    chat_history = []

    # LLM 추출 결과 먼저 출력
    print_pre_extracted_info_llm(extracted)

    print("Agentic RAG (rawtext.txt / 인메모리 FAISS)")
    print("=" * 70)
    print("종료: quit/exit/종료 | 초기화: reset/clear/초기화")

    while True:
        user_input = await asyncio.to_thread(input, "\n질문: ")
        if user_input is None:
            continue
        user_input = user_input.strip()

        if user_input.lower() in ["exit", "quit", "종료"]:
            print("시스템 종료합니다.")
            break
        if user_input.lower() in ["reset", "clear", "초기화"]:
            chat_history = []
            print("대화 내용이 초기화되었습니다.")
            print_pre_extracted_info_llm(extracted)
            continue
        if not user_input:
            continue

        try:
            print("답변: ", end="", flush=True)
            full_response = ""
            async for event in agent_executor.astream_events(
                {"input": user_input, "chat_history": chat_history},
                version="v2",
            ):
                kind = event["event"]
                if kind == "on_tool_start":
                    tool_name = event["name"]
                    print(f"\n[{tool_name}] 검색 중...", end="", flush=True)
                    print(" 완료\n답변: ", end="", flush=True)
                elif kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"].content
                    if chunk:
                        print(chunk, end="", flush=True)
                        full_response += chunk
            print()

            # 대화 기록 업데이트
            chat_history.append(HumanMessage(content=user_input))
            chat_history.append(AIMessage(content=full_response))

        except Exception as e:
            print(f"\n오류 발생: {e}")


# =========================
# 6) 실행
# =========================
if __name__ == "__main__":
    asyncio.run(run_multiturn_conversation())
