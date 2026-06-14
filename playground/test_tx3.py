class A:
    def foo(self): pass

class B:
    def __init__(self, a):
        self.a = a
    def __getattr__(self, name):
        if hasattr(self.a, name):
            return getattr(self.a, name)
        raise AttributeError(name)

b = B(A())
print("hasattr foo:", hasattr(b, "foo"))
print("hasattr bar:", hasattr(b, "bar"))
