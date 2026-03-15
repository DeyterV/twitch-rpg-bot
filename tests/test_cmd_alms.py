"""Тесты команд !команды и !милостыня."""

import time
import unittest
from unittest.mock import patch

from tests.helpers import _bot, _player, _ctx


class TestCmdCommands(unittest.IsolatedAsyncioTestCase):
    async def test_sends_message(self):
        bot = _bot()
        ctx = _ctx('user')
        await bot.cmd_commands(ctx)
        ctx.send.assert_called_once()
        self.assertIn('user', ctx.send.call_args[0][0])

    async def test_message_contains_channel_hint(self):
        bot = _bot()
        ctx = _ctx('user')
        await bot.cmd_commands(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('описание', msg)


class TestCmdAlms(unittest.IsolatedAsyncioTestCase):
    async def test_grants_gold_when_off_cooldown(self):
        p = _player(gold=0, alms_unteal=0)
        bot = _bot({'user': p})
        ctx = _ctx('user')
        with patch('random.choice', return_value=2):
            await bot.cmd_alms(ctx)
        self.assertEqual(bot.players['user']['gold'], 2)
        ctx.send.assert_called_once()

    async def test_grants_zero_gold(self):
        p = _player(gold=5, alms_unteal=0)
        bot = _bot({'user': p})
        ctx = _ctx('user')
        with patch('random.choice', return_value=0):
            await bot.cmd_alms(ctx)
        self.assertEqual(bot.players['user']['gold'], 5)

    async def test_sets_cooldown_timestamp(self):
        p = _player(alms_unteal=0)
        bot = _bot({'user': p})
        ctx = _ctx('user')
        before = time.time()
        await bot.cmd_alms(ctx)
        self.assertGreaterEqual(bot.players['user']['alms_unteal'], before + 299)

    async def test_blocked_when_on_cooldown(self):
        p = _player(gold=0, alms_unteal=time.time() + 200)
        bot = _bot({'user': p})
        ctx = _ctx('user')
        await bot.cmd_alms(ctx)
        self.assertEqual(bot.players['user']['gold'], 0)
        msg = ctx.send.call_args[0][0]
        self.assertIn('секунд', msg)

    async def test_cooldown_message_shows_remaining_time(self):
        p = _player(alms_unteal=time.time() + 100)
        bot = _bot({'user': p})
        ctx = _ctx('user')
        await bot.cmd_alms(ctx)
        msg = ctx.send.call_args[0][0]
        # remaining: int(100 - epsilon) + 1 == 100
        self.assertIn('100', msg)

    async def test_saves_players_after_alms(self):
        p = _player(alms_unteal=0)
        bot = _bot({'user': p})
        ctx = _ctx('user')
        await bot.cmd_alms(ctx)
        bot.save_players.assert_called_once()

    async def test_no_character_sends_error(self):
        bot = _bot()
        ctx = _ctx('nobody')
        await bot.cmd_alms(ctx)
        ctx.send.assert_called_once()
        self.assertIn('нет персонажа', ctx.send.call_args[0][0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
