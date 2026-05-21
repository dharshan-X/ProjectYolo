import pytest
import sqlite3
import os
from pathlib import Path
from tools.yolo_memory import TieredMemoryEngine

@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test_memory.db"
    return db_path

def test_memory_init(temp_db):
    engine = TieredMemoryEngine(db_path=temp_db)
    tables = engine.get_tables()
    assert "L1_working_memory" in tables
    assert "L2_episodic_memory" in tables
    assert "L3_semantic_memory" in tables
    assert "L4_pattern_memory" in tables

def test_memory_fts5_chaos(temp_db):
    engine = TieredMemoryEngine(db_path=temp_db)
    user_id = 1
    # Add some memories
    engine.add("My name is Alice", user_id=user_id, importance=9.0)
    engine.consolidate_memories(user_id=user_id)
    
    # Chaos queries with FTS5 special chars
    chaos_queries = [
        "Alice *",
        "Alice AND Alice",
        "Alice OR Alice",
        "\"Alice\"",
        "Alice : Alice",
        "Alice ^ Alice",
        "()",
        "!",
        "'"
    ]
    
    for q in chaos_queries:
        # Should not crash
        results = engine.search(q, filters={"user_id": user_id})
        # Basic check
        assert isinstance(results, list)

def test_memory_contradiction_resolution(temp_db):
    engine = TieredMemoryEngine(db_path=temp_db)
    user_id = 1
    
    # Initial name
    engine.add("My name is Alice", user_id=user_id, importance=9.0)
    engine.consolidate_memories(user_id=user_id)
    
    stats = engine.memory_stats(user_id=user_id)
    assert stats['L3_semantic_memory'] == 1
    
    # Contradictory name
    engine.add("My name is Bob", user_id=user_id, importance=9.0)
    engine.consolidate_memories(user_id=user_id)
    
    # Should still be 1 (Bob should have replaced Alice)
    stats = engine.memory_stats(user_id=user_id)
    assert stats['L3_semantic_memory'] == 1
    
    results = engine.get_all({"user_id": user_id})
    facts = [r['memory'] for r in results if r['id'].startswith('l3_')]
    assert "My name is Bob" in facts
    assert "Alice" not in facts[0]

def test_memory_noise_filter(temp_db):
    engine = TieredMemoryEngine(db_path=temp_db)
    user_id = 1
    
    # Very short noise
    engine.add("hi", user_id=user_id)
    stats = engine.memory_stats(user_id=user_id)
    assert stats['L2_episodic_memory'] == 0
    
    # Slightly longer but low importance
    engine.add("today is a day", user_id=user_id, importance=1.0)
    stats = engine.memory_stats(user_id=user_id)
    assert stats['L2_episodic_memory'] == 0

def test_memory_auto_consolidation(temp_db):
    engine = TieredMemoryEngine(db_path=temp_db)
    user_id = 1
    
    # Add 21 memories (threshold is 20)
    for i in range(21):
        engine.add(f"Important fact number {i}", user_id=user_id, importance=5.0)
    
    stats = engine.memory_stats(user_id=user_id)
    # L2 should be cleared and L3 should have the facts
    assert stats['L2_episodic_memory'] == 0
    assert stats['L3_semantic_memory'] == 21

def test_memory_deletion_non_existent(temp_db):
    engine = TieredMemoryEngine(db_path=temp_db)
    # Should not crash
    engine.delete("l3_99999")
    engine.delete("l2_99999")
    engine.delete("l1_non_existent")
    engine.delete("l4_99999")
    engine.delete("invalid_prefix_9999")

def test_memory_search_short_terms(temp_db):
    engine = TieredMemoryEngine(db_path=temp_db)
    user_id = 1
    engine.add("A very long fact about something", user_id=user_id, importance=5.0)
    engine.consolidate_memories(user_id=user_id)
    
    # Search with term shorter than 2 chars (engine ignores terms < 2)
    results = engine.search("A", filters={"user_id": user_id})
    assert len(results) == 0

if __name__ == "__main__":
    # Manual run
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Path(tmpdir) / "test.db"
        test_memory_init(db)
        print("test_memory_init passed")
        test_memory_fts5_chaos(db)
        print("test_memory_fts5_chaos passed")
        test_memory_contradiction_resolution(db)
        print("test_memory_contradiction_resolution passed")
        test_memory_noise_filter(db)
        print("test_memory_noise_filter passed")
        test_memory_auto_consolidation(db)
        print("test_memory_auto_consolidation passed")
        test_memory_deletion_non_existent(db)
        print("test_memory_deletion_non_existent passed")
        test_memory_search_short_terms(db)
        print("test_memory_search_short_terms passed")
        print("All memory chaos tests passed!")
