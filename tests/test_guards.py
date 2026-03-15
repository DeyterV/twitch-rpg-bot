"""Тесты защитных проверок «нет персонажа» и прочих граничных случаев."""

import time
import unittest

from tests.helpers import _bot, _player, _ctx


class TestNoCharacterGuards(unittest.IsolatedAsyncioTestCase):
    async def test_cmd_brothel_no_character(self):
        bot = _bot()
        ctx = _ctx('nobody', '!бордель')
        await bot.cmd_brothel(ctx)
        ctx.send.assert_called_once()

    async def test_cmd_heal_no_character(self):
        bot = _bot()
        ctx = _ctx('nobody', '!лечиться')
        await bot.cmd_heal(ctx)
        ctx.send.assert_called_once()

    async def test_cmd_sell_no_character(self):
        bot = _bot()
        ctx = _ctx('nobody', '!продать Меч')
        ctx.message.content = '!продать Меч'
        await bot.cmd_sell(ctx)
        ctx.send.assert_called_once()

    async def test_cmd_sell_no_item_name(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!продать')
        ctx.message.content = '!продать'
        await bot.cmd_sell(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('укажи предмет', msg)

    async def test_cmd_appraise_no_character(self):
        bot = _bot()
        ctx = _ctx('nobody', '!оценить Меч')
        ctx.message.content = '!оценить Меч'
        await bot.cmd_appraise(ctx)
        ctx.send.assert_called_once()

    async def test_cmd_appraise_no_item_name(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!оценить')
        ctx.message.content = '!оценить'
        await bot.cmd_appraise(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('укажи предмет', msg)

    async def test_cmd_appraise_item_not_in_inventory(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!оценить Магический меч')
        ctx.message.content = '!оценить Магический меч'
        await bot.cmd_appraise(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('нет предмета', msg)

    async def test_cmd_appraise_item_not_in_items(self):
        bot = _bot({'user': _player(inventory=['Камень'])})
        ctx = _ctx('user', '!оценить Камень')
        ctx.message.content = '!оценить Камень'
        await bot.cmd_appraise(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('не подлежит продаже', msg)

    async def test_cmd_steal_no_character(self):
        bot = _bot()
        ctx = _ctx('nobody', '!кража @bob Меч')
        ctx.message.content = '!кража @bob Меч'
        await bot.cmd_steal(ctx)
        ctx.send.assert_called_once()

    async def test_cmd_steal_wrong_format(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!кража @bob')
        ctx.message.content = '!кража @bob'
        await bot.cmd_steal(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('формат', msg)

    async def test_cmd_steal_target_not_found(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!кража @ghost Меч')
        ctx.message.content = '!кража @ghost Меч'
        await bot.cmd_steal(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('не имеет персонажа', msg)

    async def test_cmd_prison_no_character(self):
        bot = _bot()
        ctx = _ctx('nobody', '!взятка')
        await bot.cmd_prison(ctx)
        ctx.send.assert_called_once()

    async def test_cmd_tavern_no_character(self):
        bot = _bot()
        ctx = _ctx('nobody', '!таверна')
        await bot.cmd_tavern(ctx)
        ctx.send.assert_called_once()

    async def test_cmd_race_no_character(self):
        bot = _bot()
        ctx = _ctx('nobody', '!раса эльф')
        ctx.message.content = '!раса эльф'
        await bot.cmd_race(ctx)
        ctx.send.assert_called_once()

    async def test_cmd_race_no_name_shows_list(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!раса')
        ctx.message.content = '!раса'
        await bot.cmd_race(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('укажи расу', msg)

    async def test_cmd_class_no_character(self):
        bot = _bot()
        ctx = _ctx('nobody', '!класс воин')
        ctx.message.content = '!класс воин'
        await bot.cmd_class(ctx)
        ctx.send.assert_called_once()

    async def test_cmd_class_no_name_shows_list(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!класс')
        ctx.message.content = '!класс'
        await bot.cmd_class(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('укажи класс', msg)

    async def test_cmd_full_heal_no_character(self):
        bot = _bot()
        ctx = _ctx('nobody', '!отдых')
        await bot.cmd_full_heal(ctx)
        ctx.send.assert_called_once()

    async def test_cmd_gift_wrong_format(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!подарить bob')
        ctx.message.content = '!подарить bob'
        await bot.cmd_gift(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('формат', msg)

    async def test_cmd_gift_target_not_found(self):
        bot = _bot({'user': _player(inventory=['Деревянный меч'])})
        ctx = _ctx('user', '!подарить ghost Деревянный меч')
        ctx.message.content = '!подарить ghost Деревянный меч'
        await bot.cmd_gift(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('должен иметь персонажа', msg)

    async def test_cmd_gift_item_not_in_inventory(self):
        sender = _player(gold=500)
        receiver = _player()
        bot = _bot({'alice': sender, 'bob': receiver})
        ctx = _ctx('alice', '!подарить bob Магический меч')
        ctx.message.content = '!подарить bob Магический меч'
        await bot.cmd_gift(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('нет такого предмета', msg)

    async def test_cmd_gift_gold_invalid_amount(self):
        sender = _player(gold=500)
        receiver = _player()
        bot = _bot({'alice': sender, 'bob': receiver})
        ctx = _ctx('alice', '!подарить bob золото abc')
        ctx.message.content = '!подарить bob золото abc'
        await bot.cmd_gift(ctx)
        ctx.send.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
