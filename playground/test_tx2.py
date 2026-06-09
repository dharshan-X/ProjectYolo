from tools.yolo_memory import TieredMemoryEngine

def test_all():
    engine = TieredMemoryEngine(db_path="test_tx.db")
    
    # search
    print("Testing search...")
    res = engine.search("fact", filters={"user_id": "1"})
    print("Search results:", res)

    # get_all
    print("Testing get_all...")
    all_res = engine.get_all(filters={"user_id": "1"})
    print("Get all:", len(all_res))

if __name__ == "__main__":
    test_all()
