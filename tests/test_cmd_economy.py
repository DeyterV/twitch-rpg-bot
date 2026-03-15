"""Тесты экономических команд: !кража, !взятка, !таверна, !бордель,
!лечиться, !раса, !класс, !отдых, !черныйрынок, !купить."""

import time
import unittest
from unittest.mock import patch

import rpg_bot as rb
from tests.helpers import _bot, _player, _ctx


class TestCmdSteal(unittest.IsolatedAsyncioTestCase):
    async def test_successful_steal_transfers_item(self):
        thief = _player()
        victim = _player(inventory=['Деревянный меч'])
        bot = _bot({'thief': thief, 'victim': victim})
        ctx = _ctx('thief', '!кража @victim Деревянный меч')
        ctx.message.content = '!кража @victim Деревянный меч'
        with patch('random.random', return_value=0.0):
            await bot.cmd_steal(ctx)
        self.assertIn('Деревянный меч', bot.players['thief']['inventory'])
        self.assertNotIn('Деревянный меч', bot.players['victim']['inventory'])

    async def test_failed_steal_sends_to_prison(self):
        thief = _player()
        victim = _player(inventory=['Деревянный меч'])
        bot = _bot({'thief': thief, 'victim': victim})
        ctx = _ctx('thief', '!кража @victim Деревянный меч')
        ctx.message.content = '!кража @victim Деревянный меч'
        with patch('random.random', return_value=0.99):
            await bot.cmd_steal(ctx)
        self.assertTrue(bot.players['thief']['prison'])
        self.assertGreater(bot.players['thief']['prison_until'], time.time())

    async def test_steal_from_self_rejected(self):
        p = _player(inventory=['Деревянный меч'])
        bot = _bot({'user': p})
        ctx = _ctx('user', '!кража @user Деревянный меч')
        ctx.message.content = '!кража @user Деревянный меч'
        await bot.cmd_steal(ctx)
        ctx.send.assert_called_once()
        self.assertEqual(bot.players['user']['inventory'].count('Деревянный меч'), 1)

    async def test_steal_nonexistent_item_sends_error(self):
        thief = _player()
        victim = _player()
        bot = _bot({'thief': thief, 'victim': victim})
        ctx = _ctx('thief', '!кража @victim Дракон')
        ctx.message.content = '!кража @victim Дракон'
        await bot.cmd_steal(ctx)
        ctx.send.assert_called_once()

    async def test_amulet_increases_steal_chance(self):
        thief = _player(**{'class': 'вор'})
        thief['equipment']['amulet'] = 'Амулет удачи'
        victim = _player(inventory=['Железный меч'])
        bot = _bot({'thief': thief, 'victim': victim})
        ctx = _ctx('thief', '!кража @victim Железный меч')
        ctx.message.content = '!кража @victim Железный меч'
        with patch('random.random', return_value=0.19):
            await bot.cmd_steal(ctx)
        self.assertIn('Железный меч', bot.players['thief']['inventory'])


class TestCmdStealCooldown(unittest.IsolatedAsyncioTestCase):
    async def test_steal_blocked_by_cooldown(self):
        thief = _player(last_steal_time=time.time())
        victim = _player(inventory=['Деревянный меч'])
        bot = _bot({'user': thief, 'victim': victim})
        ctx = _ctx('user', '!кража @victim Деревянный меч')
        ctx.message.content = '!кража @victim Деревянный меч'
        await bot.cmd_steal(ctx)
        self.assertNotIn('Деревянный меч', bot.players['user']['inventory'])
        ctx.send.assert_called_once()


class TestCmdPrison(unittest.IsolatedAsyncioTestCase):
    async def test_bribe_frees_from_prison(self):
        p = _player(gold=200, prison=True, prison_until=time.time() + 300)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!взятка')
        await bot.cmd_prison(ctx)
        self.assertFalse(bot.players['user']['prison'])
        self.assertEqual(bot.players['user']['gold'], 150)

    async def test_bribe_when_not_in_prison_sends_error(self):
        p = _player(gold=200, prison=False)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!взятка')
        await bot.cmd_prison(ctx)
        self.assertEqual(bot.players['user']['gold'], 200)
        ctx.send.assert_called_once()

    async def test_bribe_not_enough_gold(self):
        p = _player(gold=10, prison=True, prison_until=time.time() + 300)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!взятка')
        await bot.cmd_prison(ctx)
        self.assertTrue(bot.players['user']['prison'])


class TestCmdTavern(unittest.IsolatedAsyncioTestCase):
    async def test_tavern_grants_attack_buff(self):
        p = _player(gold=200)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!таверна')
        await bot.cmd_tavern(ctx)
        self.assertEqual(bot.players['user']['gold'], 150)
        self.assertGreater(bot.players['user'].get('attack_buff_until', 0), time.time())

    async def test_tavern_not_enough_gold(self):
        p = _player(gold=10)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!таверна')
        await bot.cmd_tavern(ctx)
        self.assertEqual(bot.players['user']['gold'], 10)

    async def test_tavern_buff_already_active_sends_error(self):
        p = _player(gold=200, attack_buff_until=time.time() + 9999)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!таверна')
        await bot.cmd_tavern(ctx)
        self.assertEqual(bot.players['user']['gold'], 200)


class TestCmdBrothel(unittest.IsolatedAsyncioTestCase):
    async def test_brothel_grants_xp_buff(self):
        p = _player(gold=200)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!бордель')
        with patch('random.random', return_value=0.5):
            await bot.cmd_brothel(ctx)
        self.assertEqual(bot.players['user']['gold'], 100)
        self.assertGreater(bot.players['user'].get('xp_buff_until', 0), time.time())

    async def test_brothel_gives_penalty(self):
        p = _player(gold=200)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!бордель')
        with patch('random.random', return_value=0.1):
            await bot.cmd_brothel(ctx)
        self.assertTrue(bot.players['user'].get('xp_penalty', False))

    async def test_brothel_not_enough_gold(self):
        p = _player(gold=50)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!бордель')
        await bot.cmd_brothel(ctx)
        self.assertEqual(bot.players['user']['gold'], 50)

    async def test_brothel_active_buff_blocks_entry(self):
        p = _player(gold=500, xp_buff_until=time.time() + 9999)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!бордель')
        await bot.cmd_brothel(ctx)
        self.assertEqual(bot.players['user']['gold'], 500)


class TestCmdHeal(unittest.IsolatedAsyncioTestCase):
    async def test_heal_removes_xp_penalty(self):
        p = _player(gold=200, xp_penalty=True)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!лечиться')
        await bot.cmd_heal(ctx)
        self.assertFalse(bot.players['user']['xp_penalty'])
        self.assertEqual(bot.players['user']['gold'], 150)

    async def test_heal_without_penalty_sends_error(self):
        p = _player(gold=200)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!лечиться')
        await bot.cmd_heal(ctx)
        self.assertEqual(bot.players['user']['gold'], 200)


class TestCmdHealNoGold(unittest.IsolatedAsyncioTestCase):
    async def test_heal_with_penalty_but_no_gold(self):
        p = _player(gold=10, xp_penalty=True)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!лечиться')
        await bot.cmd_heal(ctx)
        self.assertTrue(bot.players['user']['xp_penalty'])
        self.assertIn('недостаточно золота', ctx.send.call_args[0][0])


class TestCmdRace(unittest.IsolatedAsyncioTestCase):
    async def test_set_race(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!раса эльф')
        ctx.message.content = '!раса эльф'
        await bot.cmd_race(ctx)
        self.assertEqual(bot.players['user']['race'], 'эльф')

    async def test_cannot_change_race(self):
        p = _player(race='человек')
        bot = _bot({'user': p})
        ctx = _ctx('user', '!раса орк')
        ctx.message.content = '!раса орк'
        await bot.cmd_race(ctx)
        self.assertEqual(bot.players['user']['race'], 'человек')

    async def test_invalid_race_sends_error(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!раса дракон')
        ctx.message.content = '!раса дракон'
        await bot.cmd_race(ctx)
        self.assertIsNone(bot.players['user']['race'])

    async def test_hp_updated_after_race_selection(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!раса орк')
        ctx.message.content = '!раса орк'
        await bot.cmd_race(ctx)
        expected = rb.calculate_hp(1) + 0
        self.assertEqual(bot.players['user']['current_hp'], expected)


class TestCmdClass(unittest.IsolatedAsyncioTestCase):
    async def test_set_class(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!класс вор')
        ctx.message.content = '!класс вор'
        await bot.cmd_class(ctx)
        self.assertEqual(bot.players['user']['class'], 'вор')

    async def test_cannot_change_class(self):
        p = _player(**{'class': 'воин'})
        bot = _bot({'user': p})
        ctx = _ctx('user', '!класс маг')
        ctx.message.content = '!класс маг'
        await bot.cmd_class(ctx)
        self.assertEqual(bot.players['user']['class'], 'воин')

    async def test_invalid_class_sends_error(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!класс паладин')
        ctx.message.content = '!класс паладин'
        await bot.cmd_class(ctx)
        self.assertIsNone(bot.players['user']['class'])

    async def test_hp_updated_after_class_selection(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!класс воин')
        ctx.message.content = '!класс воин'
        await bot.cmd_class(ctx)
        expected = rb.calculate_hp(1) + 10
        self.assertEqual(bot.players['user']['current_hp'], expected)


class TestCmdFullHeal(unittest.IsolatedAsyncioTestCase):
    async def test_restores_hp(self):
        p = _player(gold=100, current_hp=10)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!отдых')
        await bot.cmd_full_heal(ctx)
        self.assertEqual(bot.players['user']['current_hp'], rb.calculate_hp(1))
        self.assertEqual(bot.players['user']['gold'], 95)

    async def test_full_hp_not_charged(self):
        p = _player(gold=100, current_hp=rb.calculate_hp(1))
        bot = _bot({'user': p})
        ctx = _ctx('user', '!отдых')
        await bot.cmd_full_heal(ctx)
        self.assertEqual(bot.players['user']['gold'], 100)

    async def test_not_enough_gold(self):
        p = _player(gold=2, current_hp=10)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!отдых')
        await bot.cmd_full_heal(ctx)
        self.assertEqual(bot.players['user']['current_hp'], 10)


class TestCmdBlackMarket(unittest.IsolatedAsyncioTestCase):
    async def test_shows_market_items(self):
        bot = _bot({'user': _player()})
        bot.black_market_items = [
            {'name': 'Зелье лечения', 'type': 'consumable', 'price': 80, 'description': 'test'}
        ]
        bot.black_market_last_refresh = time.time()
        ctx = _ctx('user', '!черныйрынок')
        await bot.cmd_black_market(ctx)
        self.assertTrue(ctx.send.called)
        calls_text = ' '.join(c[0][0] for c in ctx.send.call_args_list)
        self.assertIn('Зелье лечения', calls_text)

    async def test_market_refreshes_when_stale(self):
        bot = _bot()
        bot.black_market_last_refresh = 0
        ctx = _ctx('user', '!черныйрынок')
        await bot.cmd_black_market(ctx)
        self.assertGreater(len(bot.black_market_items), 0)


class TestCmdBuy(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = _bot({'user': _player(gold=1000)})
        self.bot.black_market_items = [
            {'name': 'Зелье лечения', 'type': 'consumable', 'price': 80, 'description': 'test'}
        ]
        self.bot.black_market_last_refresh = time.time()

    async def test_buy_valid_item(self):
        ctx = _ctx('user', '!купить 1')
        ctx.message.content = '!купить 1'
        await self.bot.cmd_buy(ctx)
        self.assertIn('Зелье лечения', self.bot.players['user']['inventory'])
        self.assertEqual(self.bot.players['user']['gold'], 920)

    async def test_buy_not_enough_gold(self):
        self.bot.players['user']['gold'] = 10
        ctx = _ctx('user', '!купить 1')
        ctx.message.content = '!купить 1'
        await self.bot.cmd_buy(ctx)
        self.assertEqual(self.bot.players['user']['inventory'], [])

    async def test_buy_invalid_index_sends_error(self):
        ctx = _ctx('user', '!купить 99')
        ctx.message.content = '!купить 99'
        await self.bot.cmd_buy(ctx)
        self.assertEqual(self.bot.players['user']['inventory'], [])

    async def test_buy_no_character_sends_error(self):
        bot = _bot()
        ctx = _ctx('nobody', '!купить 1')
        ctx.message.content = '!купить 1'
        await bot.cmd_buy(ctx)
        ctx.send.assert_called_once()


class TestCmdBuyExtra(unittest.IsolatedAsyncioTestCase):
    async def test_bad_format_sends_error(self):
        bot = _bot({'user': _player(gold=1000)})
        bot.black_market_items = [{'name': 'Зелье', 'type': 'consumable', 'price': 10, 'description': ''}]
        bot.black_market_last_refresh = time.time()
        ctx = _ctx('user', '!купить abc')
        ctx.message.content = '!купить abc'
        await bot.cmd_buy(ctx)
        ctx.send.assert_called_once()
        self.assertIn('формат', ctx.send.call_args[0][0])

    async def test_buy_non_consumable_item(self):
        bot = _bot({'user': _player(gold=1000)})
        bot.black_market_items = [{'name': 'Особый меч', 'type': 'weapon', 'price': 50, 'description': ''}]
        bot.black_market_last_refresh = time.time()
        ctx = _ctx('user', '!купить 1')
        ctx.message.content = '!купить 1'
        await bot.cmd_buy(ctx)
        self.assertIn('Особый меч', bot.players['user']['inventory'])
        msg = ctx.send.call_args[0][0]
        self.assertIn('Особый меч', msg)


if __name__ == '__main__':
    unittest.main(verbosity=2)
