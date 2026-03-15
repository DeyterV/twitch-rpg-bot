"""Тесты сервисных методов: try_level_up, get_equipment_bonuses, check_cooldown."""

import time
import unittest

from tests.helpers import rb, _bot, _player, _ctx


class TestTryLevelUp(unittest.TestCase):
    def setUp(self):
        self.bot = _bot()

    def test_no_level_up_when_xp_insufficient(self):
        p = _player(level=1, xp=99)
        self.assertFalse(self.bot.try_level_up(p))
        self.assertEqual(p['level'], 1)
        self.assertEqual(p['xp'], 99)

    def test_single_level_up_at_threshold(self):
        p = _player(level=1, xp=100)
        self.assertTrue(self.bot.try_level_up(p))
        self.assertEqual(p['level'], 2)
        self.assertEqual(p['xp'], 0)

    def test_multiple_level_ups(self):
        # 1→2: 100 XP; 2→3: 200 XP — итого 300
        p = _player(level=1, xp=300)
        self.assertTrue(self.bot.try_level_up(p))
        self.assertEqual(p['level'], 3)
        self.assertEqual(p['xp'], 0)

    def test_hp_recalculated_after_level_up(self):
        p = _player(level=1, xp=100, current_hp=30)
        self.bot.try_level_up(p)
        self.assertEqual(p['current_hp'], rb.calculate_hp(2))  # 35

    def test_leftover_xp_preserved(self):
        p = _player(level=1, xp=150)  # 100 used, 50 remain
        self.bot.try_level_up(p)
        self.assertEqual(p['xp'], 50)


class TestGetEquipmentBonuses(unittest.TestCase):
    def setUp(self):
        self.bot = _bot()

    def test_no_equipment_no_class(self):
        p = _player()
        self.assertEqual(self.bot.get_equipment_bonuses(p), (0, 0, 0))

    def test_weapon_attack_bonus(self):
        p = _player()
        p['equipment']['weapon'] = 'Железный меч'  # +5–7 atk
        mn, mx, hp = self.bot.get_equipment_bonuses(p)
        self.assertEqual(mn, 5)
        self.assertEqual(mx, 7)
        self.assertEqual(hp, 0)

    def test_armor_hp_bonus(self):
        p = _player()
        p['equipment']['armor'] = 'Кольчуга'  # +15 hp
        mn, mx, hp = self.bot.get_equipment_bonuses(p)
        self.assertEqual(hp, 15)
        self.assertEqual(mn, 0)

    def test_pet_hp_bonus(self):
        p = _player()
        p['equipment']['pet'] = 'Слизь'  # +3 hp
        _, _, hp = self.bot.get_equipment_bonuses(p)
        self.assertEqual(hp, 3)

    def test_warrior_class_bonus(self):
        p = _player(**{'class': 'воин'})
        mn, mx, hp = self.bot.get_equipment_bonuses(p)
        self.assertEqual(mn, 2)
        self.assertEqual(mx, 5)
        self.assertEqual(hp, 10)

    def test_combined_weapon_armor_class(self):
        p = _player(**{'class': 'воин'})
        p['equipment']['weapon'] = 'Деревянный меч'  # +2–4 atk
        p['equipment']['armor'] = 'Кожаная броня'    # +10 hp
        mn, mx, hp = self.bot.get_equipment_bonuses(p)
        self.assertEqual(mn, 4)   # 2 (sword) + 2 (warrior)
        self.assertEqual(mx, 9)   # 4 (sword) + 5 (warrior)
        self.assertEqual(hp, 20)  # 10 (armor) + 10 (warrior)

    def test_amulet_zero_bonuses(self):
        p = _player()
        p['equipment']['amulet'] = 'Амулет удачи'  # 0 atk, 0 hp
        mn, mx, hp = self.bot.get_equipment_bonuses(p)
        self.assertEqual((mn, mx, hp), (0, 0, 0))


class TestCheckCooldown(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = _bot()

    async def test_allowed_when_no_previous_action(self):
        p = _player(last_xp_time=0)
        ctx = _ctx()
        result = await self.bot.check_cooldown(p, 'last_xp_time', 300, ctx)
        self.assertTrue(result)
        ctx.send.assert_not_called()

    async def test_blocked_when_on_cooldown(self):
        p = _player(last_xp_time=time.time())
        ctx = _ctx()
        result = await self.bot.check_cooldown(p, 'last_xp_time', 300, ctx)
        self.assertFalse(result)
        ctx.send.assert_called_once()

    async def test_timestamp_updated_when_allowed(self):
        p = _player(last_xp_time=0)
        ctx = _ctx()
        before = time.time()
        await self.bot.check_cooldown(p, 'last_xp_time', 300, ctx)
        self.assertGreaterEqual(p['last_xp_time'], before)

    async def test_cooldown_message_contains_seconds(self):
        p = _player(last_fight_time=time.time())
        ctx = _ctx()
        await self.bot.check_cooldown(p, 'last_fight_time', 90, ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('секунд', msg)


if __name__ == '__main__':
    unittest.main(verbosity=2)
