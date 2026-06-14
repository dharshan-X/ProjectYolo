from tools.memory_service import HybridMemoryEngine
from tools.yolo_memory import TieredMemoryEngine

class MockMem0:
    pass

hybrid = HybridMemoryEngine(MockMem0(), TieredMemoryEngine())
print("hasattr memory_stats:", hasattr(hybrid, "memory_stats"))
if hasattr(hybrid, "memory_stats"):
    print("stats:", hybrid.memory_stats(1))
