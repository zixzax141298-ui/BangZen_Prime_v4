import unittest
from decimal import Decimal

from bangzen_prime.core.errors import DomainError
from bangzen_prime.core.values import non_negative, percent, positive, unit_interval


class ValueParsingTest(unittest.TestCase):
    def test_float_rejected_for_money(self):
        with self.assertRaises(DomainError):
            positive(0.1, "price")

    def test_bool_rejected(self):
        with self.assertRaises(DomainError):
            positive(True, "price")

    def test_non_finite_rejected(self):
        for raw in ("NaN", "Infinity", "-Infinity", "sNaN"):
            with self.subTest(raw=raw), self.assertRaises(DomainError):
                positive(raw, "price")

    def test_zero_and_negative_price_rejected(self):
        for raw in ("0", "-0.5"):
            with self.subTest(raw=raw), self.assertRaises(DomainError):
                positive(raw, "price")

    def test_non_negative_accepts_zero(self):
        self.assertEqual(non_negative("0", "liq"), Decimal(0))
        with self.assertRaises(DomainError):
            non_negative("-1", "liq")

    def test_percent_boundaries(self):
        self.assertEqual(percent("0", "p"), Decimal(0))
        self.assertEqual(percent("100", "p"), Decimal(100))
        for raw in ("-0.01", "100.01"):
            with self.subTest(raw=raw), self.assertRaises(DomainError):
                percent(raw, "p")

    def test_percent_non_zero_mode(self):
        with self.assertRaises(DomainError):
            percent("0", "risk", allow_zero=False)

    def test_unit_interval_boundaries(self):
        self.assertEqual(unit_interval("1", "c"), Decimal(1))
        with self.assertRaises(DomainError):
            unit_interval("1.0001", "c")

    def test_unparseable_string_rejected(self):
        with self.assertRaises(DomainError):
            positive("12abc", "price")

    def test_unsupported_type_rejected(self):
        with self.assertRaises(DomainError):
            positive(["1"], "price")


if __name__ == "__main__":
    unittest.main()
