import unittest
from services import state_store


class DummyWheel:
    def __init__(self, txt):
        self._txt = txt
        self.result = type("R", (), {"text": lambda self_inner: self._txt, "setText": lambda self_inner, v: None})()


class DummyMW:
    def __init__(self):
        self.summary = type("S", (), {"text": lambda self_inner: "sum", "setText": lambda self_inner, v: None})()
        self.tank = DummyWheel("t")
        self.dps = DummyWheel("d")
        self.support = DummyWheel("s")
        self.hero_ban_active = False
        self.current_mode = "players"
        self._mode_results = {}


if __name__ == "__main__":
    unittest.main()
