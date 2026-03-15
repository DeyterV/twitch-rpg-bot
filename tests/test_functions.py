"""Тесты чистых функций calculate_hp и calculate_damage."""

import unittest

from tests.helpers import rb


class TestCalculateHp(unittest.TestCase):
    def test_level_1(self):
        self.assertEqual(rb.calculate_hp(1), 30)

    def test_level_5(self):
        self.assertEqual(rb.calculate_hp(5), 50)

    def test_level_10(self):
        self.assertEqual(rb.calculate_hp(10), 75)

    def test_formula_for_all_levels(self):
        for lvl in range(1, 21):
            self.assertEqual(rb.calculate_hp(lvl), 30 + (lvl - 1) * 5)


class TestCalculateDamage(unittest.TestCase):
    def test_level_1_within_range(self):
        for _ in range(100):
            dmg = rb.calculate_damage(1)
            self.assertGreaterEqual(dmg, 7)   # 5 + 1*2
            self.assertLessEqual(dmg, 13)     # 10 + 1*3

    def test_level_10_within_range(self):
        for _ in range(100):
            dmg = rb.calculate_damage(10)
            self.assertGreaterEqual(dmg, 25)  # 5 + 10*2
            self.assertLessEqual(dmg, 40)     # 10 + 10*3

    def test_returns_int(self):
        self.assertIsInstance(rb.calculate_damage(3), int)


if __name__ == '__main__':
    unittest.main(verbosity=2)
