from prompt_builder import _derive_identity_hints
lines = [
    "user: i am dharshan\nassistant: Hello, Dharshan. How can I assist you today?",
    "user: my name id dharshan\nassistant: Hello Dharshan. How can I assist you today?"
]
print(_derive_identity_hints(lines))
