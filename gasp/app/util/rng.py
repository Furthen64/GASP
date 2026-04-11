import random

class RNG:
    def __init__(self, seed=42):
        self._rng = random.Random(seed)
        self._seed = seed

    def seed(self, s):
        self._seed = s
        self._rng.seed(s)

    def get_state(self):
        return self._rng.getstate()

    def set_state(self, state):
        self._rng.setstate(state)

    def randint(self, a, b):
        return self._rng.randint(a, b)

    def random(self):
        return self._rng.random()

    def choice(self, seq):
        return self._rng.choice(seq)

    def shuffle(self, lst):
        self._rng.shuffle(lst)
