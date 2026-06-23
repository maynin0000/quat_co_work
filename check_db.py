import chromadb

def check_database():
    # 로컬에서 접근하니까 아까 우리가 맞춘 포트(8002)로 접속
    client = chromadb.HttpClient(host="127.0.0.1", port=8002)
    
    # 컬렉션 가져오기
    collection = client.get_collection(name="paper_strategies")
    
    # 안에 있는 데이터 싹 다 가져오기
    results = collection.get()
    
    print("\n✅ [ChromaDB 확인 결과]")
    print(f"총 데이터 개수: {len(results['ids'])}개\n")
    
    for i in range(len(results['ids'])):
        print(f"[{i+1}] ID: {results['ids'][i]}")
        print(f"   본문: {results['documents'][i]}")
        print(f"   메타데이터: {results['metadatas'][i]}\n")
        print("-" * 50)

if __name__ == "__main__":
    check_database()