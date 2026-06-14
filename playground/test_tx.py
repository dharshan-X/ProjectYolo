from tools.yolo_memory import TieredMemoryEngine

def test_add():
    engine = TieredMemoryEngine(db_path="test_tx.db")
    print("Testing add()...")
    engine.add("My name is test", "1")
    print("Added first memory successfully.")
    for i in range(25):
        engine.add(f"Important fact {i}", "1")
    print("Added 25 memories successfully.")

if __name__ == "__main__":
    test_add()
