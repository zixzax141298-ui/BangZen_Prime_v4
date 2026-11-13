class SecondLifeStrategy:
    def evaluate(self, *args, **kwargs):
        from dataclasses import dataclass
        @dataclass
        class R: is_reviving: bool = False
        return R()
