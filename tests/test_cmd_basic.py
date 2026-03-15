"""Тесты базовых команд: !старт, !статус, !опыт, !топ."""

import time
import unittest

from tests.helpers import _bot, _player, _ctx


class TestCmdStart(unittest.IsolatedAsyncioTestCase):
    async def test_creates_new_player(self):
        bot = _bot()
        ctx = _ctx('newuser', '!старт')
        await bot.cmd_start(ctx)
        self.assertIn('newuser', bot.players)
        self.assertEqual(bot.players['newuser']['level'], 1)
        self.assertEqual(bot.players['newuser']['xp'], 0)
        self.assertEqual(bot.players['newuser']['gold'], 0)
        ctx.send.assert_called_once()

    async def test_rejects_existing_player(self):
        bot = _bot({'alice': _player()})
        ctx = _ctx('alice', '!старт')
        await bot.cmd_start(ctx)
        ctx.send.assert_called_once()
        self.assertIn('уже', ctx.send.call_args[0][0])

    async def test_new_player_has_correct_equipment_slots(self):
        bot = _bot()
        ctx = _ctx('newguy', '!старт')
        await bot.cmd_start(ctx)
        eq = bot.players['newguy']['equipment']
        for slot in ('weapon', 'armor', 'helmet', 'pet', 'amulet'):
            self.assertIsNone(eq[slot])


class TestCmdStatus(unittest.IsolatedAsyncioTestCase):
    async def test_shows_own_status(self):
        bot = _bot({'hero': _player(level=3, xp=50, gold=200)})
        ctx = _ctx('hero', '!статус')
        await bot.cmd_status(ctx)
        self.assertTrue(ctx.send.called)
        msg = ctx.send.call_args_list[0][0][0]
        self.assertIn('hero', msg)
        self.assertIn('3', msg)

    async def test_nonexistent_player_sends_error(self):
        bot = _bot()
        ctx = _ctx('ghost', '!статус')
        await bot.cmd_status(ctx)
        ctx.send.assert_called_once()

    async def test_shows_target_player(self):
        bot = _bot({'alice': _player(level=7)})
        ctx = _ctx('bob', '!статус @alice')
        ctx.message.content = '!статус @alice'
        await bot.cmd_status(ctx)
        msg = ctx.send.call_args_list[0][0][0]
        self.assertIn('alice', msg)

    async def test_shows_active_prison_effect(self):
        p = _player(prison=True, prison_until=time.time() + 300)
        bot = _bot({'jailed': p})
        ctx = _ctx('jailed', '!статус')
        await bot.cmd_status(ctx)
        calls = [c[0][0] for c in ctx.send.call_args_list]
        self.assertTrue(any('тюрьм' in m for m in calls))


class TestCmdStatusExtra(unittest.IsolatedAsyncioTestCase):
    async def test_shows_race_and_class(self):
        p = _player(race='эльф', **{'class': 'воин'})
        bot = _bot({'user': p})
        ctx = _ctx('user', '!статус')
        await bot.cmd_status(ctx)
        all_text = ' '.join(c[0][0] for c in ctx.send.call_args_list)
        self.assertIn('эльф', all_text)
        self.assertIn('воин', all_text)

    async def test_shows_xp_buff_effect(self):
        p = _player(xp_buff_until=time.time() + 9999)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!статус')
        await bot.cmd_status(ctx)
        all_text = ' '.join(c[0][0] for c in ctx.send.call_args_list)
        self.assertIn('+50% XP', all_text)

    async def test_shows_xp_penalty_effect(self):
        p = _player(xp_penalty=True)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!статус')
        await bot.cmd_status(ctx)
        all_text = ' '.join(c[0][0] for c in ctx.send.call_args_list)
        self.assertIn('-50% XP', all_text)

    async def test_shows_attack_buff_effect(self):
        p = _player(attack_buff_until=time.time() + 9999)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!статус')
        await bot.cmd_status(ctx)
        all_text = ' '.join(c[0][0] for c in ctx.send.call_args_list)
        self.assertIn('+10% урона', all_text)


class TestCmdXp(unittest.IsolatedAsyncioTestCase):
    async def test_grants_base_xp(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!опыт')
        await bot.cmd_xp(ctx)
        self.assertEqual(bot.players['user']['xp'], 50)
        ctx.send.assert_called_once()

    async def test_cooldown_blocks_xp_gain(self):
        p = _player(last_xp_time=time.time())
        bot = _bot({'user': p})
        ctx = _ctx('user', '!опыт')
        await bot.cmd_xp(ctx)
        self.assertEqual(p['xp'], 0)

    async def test_xp_buff_multiplies_xp(self):
        p = _player(xp_buff_until=time.time() + 9999)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!опыт')
        await bot.cmd_xp(ctx)
        self.assertEqual(bot.players['user']['xp'], 75)  # 50 * 1.5

    async def test_xp_penalty_halves_xp(self):
        p = _player(xp_penalty=True)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!опыт')
        await bot.cmd_xp(ctx)
        self.assertEqual(bot.players['user']['xp'], 25)  # 50 * 0.5

    async def test_no_character_sends_message(self):
        bot = _bot()
        ctx = _ctx('nobody', '!опыт')
        await bot.cmd_xp(ctx)
        ctx.send.assert_called_once()

    async def test_elf_race_bonus(self):
        p = _player(race='эльф')  # +10% xp
        bot = _bot({'user': p})
        ctx = _ctx('user', '!опыт')
        await bot.cmd_xp(ctx)
        self.assertEqual(bot.players['user']['xp'], 55)  # int(50 * 1.1)

    async def test_level_up_on_xp_gain(self):
        p = _player(xp=95)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!опыт')
        await bot.cmd_xp(ctx)
        self.assertEqual(bot.players['user']['level'], 2)


class TestCmdTop(unittest.IsolatedAsyncioTestCase):
    async def test_shows_top_players_sorted(self):
        players = {f'p{i}': _player(level=i) for i in range(1, 6)}
        bot = _bot(players)
        ctx = _ctx('p1', '!топ')
        await bot.cmd_top(ctx)
        ctx.send.assert_called_once()
        msg = ctx.send.call_args[0][0]
        self.assertIn('p5', msg)

    async def test_empty_players_sends_message(self):
        bot = _bot()
        ctx = _ctx('user', '!топ')
        await bot.cmd_top(ctx)
        ctx.send.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
