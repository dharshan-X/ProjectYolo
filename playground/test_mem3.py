from tools.yolo_memory import TieredMemoryEngine
engine = TieredMemoryEngine()
print(engine.memory_stats(1))
print(engine.memory_stats("1"))
print(engine.memory_stats(7118893097))
print(engine.memory_stats("7118893097"))
