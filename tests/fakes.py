"""Scripted LLM stand-in for agent tests."""


class FakeLLM:
    """Returns scripted outputs keyed by schema class (a list is consumed in order)."""

    def __init__(self, **by_schema):
        self.by = {k: (list(v) if isinstance(v, list) else v) for k, v in by_schema.items()}
        self.prompts = []

    def generate(self, prompt, schema, system=None):
        self.prompts.append(prompt)
        v = self.by[schema.__name__]
        return v.pop(0) if isinstance(v, list) else v
