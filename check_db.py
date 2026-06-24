import chromadb
import os

DB_PATH = "./chroma_db" 
print(f"🔍 탐색 경로: {os.path.abspath(DB_PATH)}")

try:
    client = chromadb.PersistentClient(path=DB_PATH)
    collections = client.list_collections()
    
    print(f"\n📂 연결된 DB에 있는 컬렉션 목록 (총 {len(collections)}개):")
    
    for c in collections:
        # 이 부분이 핵심입니다! 실제 저장된 컬렉션 이름들을 전부 출력해줍니다.
        print(f"   👉 발견된 이름: '{c.name}'") 
            
except Exception as e:
    print(f"\n🚨 에러 발생: {e}")