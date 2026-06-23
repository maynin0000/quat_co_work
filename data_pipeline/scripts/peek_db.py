import chromadb
import json

def peek_chromadb():
    print("🔍 [ChromaDB] 적재된 데이터 구경하기...")
    
    # 아까 로그를 보니 ChromaDB가 8002번 포트에서 돌고 있음
    client = chromadb.HttpClient(host="127.0.0.1", port=8002)
    
    try:
        # 컬렉션 이름은 로그에서 유추한 'paper_strategies'
        collection = client.get_collection("paper_strategies")
        
        # 전체 개수 확인
        total_count = collection.count()
        print(f"✅ 현재 저장된 총 전략(Chunk) 개수: {total_count}개\n")
        
        # 최신 데이터 3개만 살짝 꺼내오기
        # completeness가 0보다 큰(즉, 정상적으로 추출된) 진짜 전략만 3개 가져와!
        results = collection.get(
            where={"completeness": {"$gt": 0.0}}, 
            limit=3
        )
        
        print("================ [데이터 샘플 3건] ================")
        for i in range(len(results['ids'])):
            print(f"📌 [ID] : {results['ids'][i]}")
            print(f"📊 [메타데이터] : {json.dumps(results['metadatas'][i], ensure_ascii=False)}")
            print(f"📄 [본문 텍스트] :\n{results['documents'][i]}")
            print("-" * 60)
            
    except Exception as e:
        print(f"🚨 DB 조회 실패: {e}")

if __name__ == "__main__":
    peek_chromadb()