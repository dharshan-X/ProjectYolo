from tools.yolo_memory import TieredMemoryEngine
engine = TieredMemoryEngine()
print("Stats for 1:", engine.memory_stats(1))
print("Stats for '1':", engine.memory_stats("1"))
