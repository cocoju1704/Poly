"""
청킹 테스트 파일
split_text_with_tables 함수를 사용하여 청킹된 문서들을 확인할 수 있는 테스트 스크립트
"""

import json
import os
from datetime import datetime
from healthcare_chatbot import HealthCareChatbot

# 스크립트 파일의 디렉토리 경로 (절대 경로)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 프로젝트 루트 디렉토리 (crawler의 상위 디렉토리)
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
# 기본 output 디렉토리 경로
DEFAULT_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
# 기본 데이터 파일 경로
DEFAULT_DATA_FILE = os.path.join(DEFAULT_OUTPUT_DIR, "structured_data_강남구.json")


def test_chunking(data_file: str = None, output_dir: str = None, max_items: int = 5):
    """
    청킹 테스트를 실행하고 결과를 파일로 저장합니다.
    
    Args:
        data_file: JSON 데이터 파일 경로 (없으면 강남구 데이터 사용)
        output_dir: 출력 디렉토리 (없으면 기본 output 디렉토리 사용)
        max_items: 테스트할 최대 아이템 수 (기본값: 5)
    """
    # 출력 디렉토리 설정
    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_DIR
    
    # 데이터 파일 경로 설정
    if data_file is None:
        data_file = DEFAULT_DATA_FILE
    
    if not os.path.exists(data_file):
        print(f"❌ 데이터 파일을 찾을 수 없습니다: {data_file}")
        return
    
    print("\n" + "=" * 80)
    print("🧪 청킹 테스트 시작")
    print("=" * 80)
    print(f"데이터 파일: {data_file}")
    print(f"최대 테스트 아이템 수: {max_items}")
    
    # 챗봇 인스턴스 생성
    chatbot = HealthCareChatbot(output_dir=output_dir)
    
    # 데이터 로드
    print("\n📂 데이터 로드 중...")
    structured_data = chatbot.load_data(data_file)
    print(f"✅ {len(structured_data)}개 문서 로드 완료")
    
    # 테스트할 아이템 선택
    test_items = structured_data[:max_items] if len(structured_data) >= max_items else structured_data
    
    # 청킹 결과 저장용 리스트
    chunking_results = []
    
    print(f"\n📝 청킹 테스트 시작 (총 {len(test_items)}개 아이템)")
    print("=" * 80)
    
    for idx, item in enumerate(test_items, 1):
        raw_text = item.get("raw_text", "")
        if not raw_text:
            print(f"\n[{idx}] 제목: {item.get('title', 'N/A')} - raw_text가 비어있습니다.")
            continue
        
        print(f"\n[{idx}] 제목: {item.get('title', 'N/A')}")
        print(f"    지역: {item.get('region', 'N/A')}")
        print(f"    원본 텍스트 길이: {len(raw_text):,}자")
        
        # 청킹 실행
        chunks = chatbot.split_text_with_tables(
            raw_text,
            chunk_size=800,
            overlap=120
        )
        
        print(f"    생성된 청크 수: {len(chunks)}개")
        
        # 각 청크 정보 출력
        chunk_details = []
        for chunk_idx, chunk in enumerate(chunks, 1):
            chunk_length = len(chunk)
            is_table = "|" in chunk and chunk.count("|") >= 2
            chunk_type = "표" if is_table else "텍스트"
            
            # 청크 미리보기 (처음 100자)
            preview = chunk[:100].replace("\n", " ").strip()
            if len(chunk) > 100:
                preview += "..."
            
            chunk_info = {
                "chunk_number": chunk_idx,
                "type": chunk_type,
                "length": chunk_length,
                "preview": preview,
                "content": chunk
            }
            chunk_details.append(chunk_info)
            
            print(f"      청크 {chunk_idx} ({chunk_type}): {chunk_length:,}자 - {preview}")
        
        # 결과 저장
        result_item = {
            "item_id": item.get("id", ""),
            "title": item.get("title", ""),
            "region": item.get("region", ""),
            "source_url": item.get("source_url", ""),
            "original_length": len(raw_text),
            "chunk_count": len(chunks),
            "chunks": chunk_details
        }
        chunking_results.append(result_item)
    
    # 결과를 JSON 파일로 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"chunking_test_result_{timestamp}.json")
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "test_info": {
                "data_file": data_file,
                "test_date": datetime.now().isoformat(),
                "tested_items_count": len(test_items),
                "chunking_params": {
                    "chunk_size": 800,
                    "overlap": 120
                }
            },
            "results": chunking_results
        }, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 80)
    print("✅ 청킹 테스트 완료")
    print("=" * 80)
    print(f"📄 결과 파일: {output_file}")
    
    # 요약 정보 출력
    total_chunks = sum(len(r["chunks"]) for r in chunking_results)
    total_text_chunks = sum(1 for r in chunking_results for c in r["chunks"] if c["type"] == "텍스트")
    total_table_chunks = sum(1 for r in chunking_results for c in r["chunks"] if c["type"] == "표")
    
    print(f"\n📊 요약:")
    print(f"  - 테스트된 아이템 수: {len(chunking_results)}개")
    print(f"  - 총 생성된 청크 수: {total_chunks}개")
    print(f"  - 텍스트 청크: {total_text_chunks}개")
    print(f"  - 표 청크: {total_table_chunks}개")
    
    # 상세 보고서 생성 (텍스트 파일)
    report_file = os.path.join(output_dir, f"chunking_test_report_{timestamp}.txt")
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("청킹 테스트 상세 보고서\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"테스트 날짜: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"데이터 파일: {data_file}\n")
        f.write(f"테스트된 아이템 수: {len(chunking_results)}개\n")
        f.write(f"총 청크 수: {total_chunks}개\n")
        f.write(f"텍스트 청크: {total_text_chunks}개\n")
        f.write(f"표 청크: {total_table_chunks}개\n\n")
        f.write("=" * 80 + "\n\n")
        
        for item_idx, result in enumerate(chunking_results, 1):
            f.write(f"\n[{item_idx}] {result['title']}\n")
            f.write(f"지역: {result['region']}\n")
            f.write(f"원본 길이: {result['original_length']:,}자\n")
            f.write(f"청크 수: {result['chunk_count']}개\n")
            f.write(f"URL: {result['source_url']}\n")
            f.write("-" * 80 + "\n\n")
            
            for chunk in result['chunks']:
                f.write(f"  [청크 {chunk['chunk_number']}] ({chunk['type']}, {chunk['length']:,}자)\n")
                f.write("  " + "-" * 76 + "\n")
                # 청크 내용을 들여쓰기로 출력
                for line in chunk['content'].split('\n'):
                    f.write(f"  {line}\n")
                f.write("\n")
    
    print(f"📋 상세 보고서: {report_file}")


def main():
    """메인 실행 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="청킹 테스트 - split_text_with_tables 함수 테스트"
    )
    parser.add_argument(
        "--data-file",
        type=str,
        default=None,
        help=f"테스트할 JSON 데이터 파일 경로 (기본값: {DEFAULT_DATA_FILE})"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help=f"출력 디렉토리 (기본값: {DEFAULT_OUTPUT_DIR})"
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=5,
        help="테스트할 최대 아이템 수 (기본값: 5)"
    )
    
    args = parser.parse_args()
    
    try:
        test_chunking(
            data_file=args.data_file,
            output_dir=args.output_dir,
            max_items=args.max_items
        )
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

