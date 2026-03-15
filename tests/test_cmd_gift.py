"""Тесты команды !подарить."""

import unittest

from tests.helpers import _bot, _player, _ctx


class TestCmdGift(unittest.IsolatedAsyncioTestCase):

    async def test_no_character_sends_error(self):
        bot = _bot()
        ctx = _ctx('nobody', '!подарить alice Железный меч')
        await bot.cmd_gift(ctx)
        ctx.send.assert_called_once()
        self.assertIn('нет персонажа', ctx.send.call_args[0][0])

    async def test_wrong_format_sends_hint(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!подарить')
        await bot.cmd_gift(ctx)
        ctx.send.assert_called_once()
        self.assertIn('формат', ctx.send.call_args[0][0])

    async def test_target_has_no_character(self):
        bot = _bot({'user': _player(inventory=['Железный меч'])})
        ctx = _ctx('user', '!подарить ghost Железный меч')
        await bot.cmd_gift(ctx)
        self.assertIn('должен иметь персонажа', ctx.send.call_args[0][0])

    async def test_transfer_item_success(self):
        p1 = _player(inventory=['Железный меч'])
        p2 = _player(inventory=[])
        bot = _bot({'user': p1, 'alice': p2})
        ctx = _ctx('user', '!подарить alice Железный меч')
        await bot.cmd_gift(ctx)
        self.assertNotIn('Железный меч', bot.players['user']['inventory'])
        self.assertIn('Железный меч', bot.players['alice']['inventory'])
        self.assertIn('передал', ctx.send.call_args[0][0])
        bot.save_players.assert_called_once()

    async def test_transfer_item_not_in_inventory(self):
        p1 = _player(inventory=[])
        p2 = _player()
        bot = _bot({'user': p1, 'alice': p2})
        ctx = _ctx('user', '!подарить alice Железный меч')
        await bot.cmd_gift(ctx)
        self.assertIn('нет такого предмета', ctx.send.call_args[0][0])

    async def test_gift_gold_success(self):
        p1 = _player(gold=50)
        p2 = _player(gold=10)
        bot = _bot({'user': p1, 'alice': p2})
        ctx = _ctx('user', '!подарить alice Золото 30')
        await bot.cmd_gift(ctx)
        self.assertEqual(bot.players['user']['gold'], 20)
        self.assertEqual(bot.players['alice']['gold'], 40)
        self.assertIn('золотых монет', ctx.send.call_args[0][0])
        bot.save_players.assert_called_once()

    async def test_gift_gold_not_enough(self):
        p1 = _player(gold=5)
        p2 = _player(gold=0)
        bot = _bot({'user': p1, 'alice': p2})
        ctx = _ctx('user', '!подарить alice Золото 100')
        await bot.cmd_gift(ctx)
        self.assertEqual(bot.players['user']['gold'], 5)
        self.assertIn('нет столько золота', ctx.send.call_args[0][0])

    async def test_gift_gold_invalid_amount(self):
        p1 = _player(gold=50)
        p2 = _player()
        bot = _bot({'user': p1, 'alice': p2})
        ctx = _ctx('user', '!подарить alice Золото много')
        await bot.cmd_gift(ctx)
        self.assertIn('понял', ctx.send.call_args[0][0])

    async def test_gift_gold_missing_amount(self):
        p1 = _player(gold=50)
        p2 = _player()
        bot = _bot({'user': p1, 'alice': p2})
        ctx = _ctx('user', '!подарить alice Золото')
        await bot.cmd_gift(ctx)
        self.assertIn('понял', ctx.send.call_args[0][0])

    async def test_item_name_capitalized(self):
        """capitalize() нормализует ввод: 'железный меч' → 'Железный меч'."""
        p1 = _player(inventory=['Железный меч'])
        p2 = _player(inventory=[])
        bot = _bot({'user': p1, 'alice': p2})
        ctx = _ctx('user', '!подарить alice железный меч')
        await bot.cmd_gift(ctx)
        self.assertNotIn('Железный меч', bot.players['user']['inventory'])
        self.assertIn('Железный меч', bot.players['alice']['inventory'])

    async def test_gift_gold_boundary_exact_amount(self):
        """Можно подарить ровно столько, сколько есть (amount <= gold)."""
        p1 = _player(gold=50)
        p2 = _player(gold=0)
        bot = _bot({'user': p1, 'alice': p2})
        ctx = _ctx('user', '!подарить alice Золото 50')
        await bot.cmd_gift(ctx)
        self.assertEqual(bot.players['user']['gold'], 0)
        self.assertEqual(bot.players['alice']['gold'], 50)


if __name__ == '__main__':
    unittest.main(verbosity=2)
