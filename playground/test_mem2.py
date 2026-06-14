from tools.memory_service import get_memory
from tools.yolo_memory import TieredMemoryEngine
from tools.memory_ops import memory_list

memory = get_memory()
print("get_memory type:", type(memory))
print("isinstance TieredMemoryEngine:", isinstance(memory, TieredMemoryEngine))

res = memory_list(1)
print("memory_list output:\n", res)
