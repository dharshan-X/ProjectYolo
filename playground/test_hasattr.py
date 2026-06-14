class A:
    def method_a(self): pass

class B:
    def __init__(self):
        self.a = A()
    def __getattr__(self, name):
        if hasattr(self.a, name):
            return getattr(self.a, name)
        raise AttributeError(name)

b = B()
print("hasattr method_a:", hasattr(b, "method_a"))
