"""Тесты команд инвентаря: !надеть, !снять, !использовать, !инвентарь,
!экипировка, !продать, !оценить, !описание, !подарить."""

import unittest

import rpg_bot as rb
from tests.helpers import _bot, _player, _ctx


class TestCmdEquip(unittest.IsolatedAsyncioTestCase):
    async def test_equip_from_inventory(self):
        p = _player(inventory=['Железный меч'])
        bot = _bot({'user': p})
        ctx = _ctx('user', '!надеть Железный меч')
        ctx.message.content = '!надеть Железный меч'
        await bot.cmd_equip(ctx)
        self.assertEqual(bot.players['user']['equipment']['weapon'], 'Железный меч')
        self.assertNotIn('Железный меч', bot.players['user']['inventory'])

    async def test_replace_equipped_item(self):
        p = _player(inventory=['Орочий топор'])
        p['equipment']['weapon'] = 'Деревянный меч'
        bot = _bot({'user': p})
        ctx = _ctx('user', '!надеть Орочий топор')
        ctx.message.content = '!надеть Орочий топор'
        await bot.cmd_equip(ctx)
        self.assertEqual(bot.players['user']['equipment']['weapon'], 'Орочий топор')
        self.assertIn('Деревянный меч', bot.players['user']['inventory'])

    async def test_equip_item_not_in_inventory(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!надеть Железный меч')
        ctx.message.content = '!надеть Железный меч'
        await bot.cmd_equip(ctx)
        ctx.send.assert_called_once()
        self.assertIsNone(bot.players['user']['equipment']['weapon'])

    async def test_cannot_equip_consumable(self):
        p = _player(inventory=['Зелье лечения'])
        bot = _bot({'user': p})
        ctx = _ctx('user', '!надеть Зелье лечения')
        ctx.message.content = '!надеть Зелье лечения'
        await bot.cmd_equip(ctx)
        self.assertIsNone(bot.players['user']['equipment'].get('consumable'))
        self.assertIn('Зелье лечения', bot.players['user']['inventory'])


class TestCmdEquipExtra(unittest.IsolatedAsyncioTestCase):
    async def test_equip_no_character(self):
        bot = _bot()
        ctx = _ctx('nobody', '!надеть Меч')
        ctx.message.content = '!надеть Меч'
        await bot.cmd_equip(ctx)
        ctx.send.assert_called_once()

    async def test_equip_item_not_in_items_dict(self):
        bot = _bot({'user': _player(inventory=['Камень'])})
        ctx = _ctx('user', '!надеть Камень')
        ctx.message.content = '!надеть Камень'
        await bot.cmd_equip(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('не может быть надет', msg)

    async def test_equip_already_equipped(self):
        p = _player(inventory=['Деревянный меч'],
                    equipment={**{s: None for s in ('armor', 'helmet', 'pet', 'amulet')}, 'weapon': 'Деревянный меч'})
        bot = _bot({'user': p})
        ctx = _ctx('user', '!надеть Деревянный меч')
        ctx.message.content = '!надеть Деревянный меч'
        await bot.cmd_equip(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('уже надет', msg)


class TestCmdUnequip(unittest.IsolatedAsyncioTestCase):
    async def test_unequip_moves_to_inventory(self):
        p = _player()
        p['equipment']['weapon'] = 'Железный меч'
        bot = _bot({'user': p})
        ctx = _ctx('user', '!снять weapon')
        ctx.message.content = '!снять weapon'
        await bot.cmd_unequip(ctx)
        self.assertIsNone(bot.players['user']['equipment']['weapon'])
        self.assertIn('Железный меч', bot.players['user']['inventory'])

    async def test_unequip_empty_slot_sends_message(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!снять weapon')
        ctx.message.content = '!снять weapon'
        await bot.cmd_unequip(ctx)
        ctx.send.assert_called_once()


class TestCmdUnequipExtra(unittest.IsolatedAsyncioTestCase):
    async def test_unequip_no_character(self):
        bot = _bot()
        ctx = _ctx('nobody', '!снять weapon')
        ctx.message.content = '!снять weapon'
        await bot.cmd_unequip(ctx)
        ctx.send.assert_called_once()

    async def test_unequip_no_slot_given(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!снять')
        ctx.message.content = '!снять'
        await bot.cmd_unequip(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('укажи слот', msg)


class TestCmdUse(unittest.IsolatedAsyncioTestCase):
    async def test_healing_potion_restores_hp(self):
        p = _player(inventory=['Зелье лечения'], current_hp=5)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!использовать Зелье лечения')
        ctx.message.content = '!использовать Зелье лечения'
        await bot.cmd_use(ctx)
        self.assertEqual(bot.players['user']['current_hp'], 30)
        self.assertNotIn('Зелье лечения', bot.players['user']['inventory'])

    async def test_healing_potion_capped_at_max_hp(self):
        p = _player(inventory=['Зелье лечения'], current_hp=25)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!использовать Зелье лечения')
        ctx.message.content = '!использовать Зелье лечения'
        await bot.cmd_use(ctx)
        self.assertEqual(bot.players['user']['current_hp'], rb.calculate_hp(1))

    async def test_use_non_consumable_sends_error(self):
        p = _player(inventory=['Железный меч'])
        bot = _bot({'user': p})
        ctx = _ctx('user', '!использовать Железный меч')
        ctx.message.content = '!использовать Железный меч'
        await bot.cmd_use(ctx)
        ctx.send.assert_called_once()
        self.assertIn('Железный меч', bot.players['user']['inventory'])


class TestCmdUseExtra(unittest.IsolatedAsyncioTestCase):
    async def test_use_no_character(self):
        bot = _bot()
        ctx = _ctx('nobody', '!использовать Зелье')
        ctx.message.content = '!использовать Зелье'
        await bot.cmd_use(ctx)
        ctx.send.assert_called_once()

    async def test_use_no_item_name(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!использовать')
        ctx.message.content = '!использовать'
        await bot.cmd_use(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('укажи предмет', msg)

    async def test_use_item_not_in_inventory(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!использовать Зелье лечения')
        ctx.message.content = '!использовать Зелье лечения'
        await bot.cmd_use(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('нет предмета', msg)


class TestCmdInventory(unittest.IsolatedAsyncioTestCase):
    async def test_shows_items(self):
        p = _player(inventory=['Железный меч', 'Зелье лечения'])
        bot = _bot({'user': p})
        ctx = _ctx('user', '!инвентарь')
        await bot.cmd_inventory(ctx)
        ctx.send.assert_called_once()
        msg = ctx.send.call_args[0][0]
        self.assertIn('Железный меч', msg)

    async def test_empty_inventory_sends_message(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!инвентарь')
        await bot.cmd_inventory(ctx)
        ctx.send.assert_called_once()

    async def test_duplicates_shown_with_count(self):
        p = _player(inventory=['Зелье лечения', 'Зелье лечения'])
        bot = _bot({'user': p})
        ctx = _ctx('user', '!инвентарь')
        await bot.cmd_inventory(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('x2', msg)


class TestCmdInventoryEquipmentNoChar(unittest.IsolatedAsyncioTestCase):
    async def test_inventory_no_character(self):
        bot = _bot()
        ctx = _ctx('nobody', '!инвентарь')
        await bot.cmd_inventory(ctx)
        ctx.send.assert_called_once()
        self.assertIn('нет персонажа', ctx.send.call_args[0][0])

    async def test_equipment_no_character(self):
        bot = _bot()
        ctx = _ctx('nobody', '!экипировка')
        await bot.cmd_equipment(ctx)
        ctx.send.assert_called_once()
        self.assertIn('нет персонажа', ctx.send.call_args[0][0])


class TestCmdEquipment(unittest.IsolatedAsyncioTestCase):
    async def test_shows_all_slots(self):
        p = _player()
        p['equipment']['weapon'] = 'Железный меч'
        bot = _bot({'user': p})
        ctx = _ctx('user', '!экипировка')
        await bot.cmd_equipment(ctx)
        ctx.send.assert_called_once()
        msg = ctx.send.call_args[0][0]
        self.assertIn('Железный меч', msg)


class TestCmdSell(unittest.IsolatedAsyncioTestCase):
    async def test_sell_item_adds_gold(self):
        p = _player(inventory=['Железный меч'], gold=0)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!продать Железный меч')
        ctx.message.content = '!продать Железный меч'
        await bot.cmd_sell(ctx)
        self.assertNotIn('Железный меч', bot.players['user']['inventory'])
        self.assertEqual(bot.players['user']['gold'], 40)  # 80 // 2

    async def test_sell_nonexistent_item_sends_error(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!продать Железный меч')
        ctx.message.content = '!продать Железный меч'
        await bot.cmd_sell(ctx)
        ctx.send.assert_called_once()

    async def test_sell_unpriced_item_sends_error(self):
        p = _player(inventory=['Кость'])
        bot = _bot({'user': p})
        ctx = _ctx('user', '!продать Кость')
        ctx.message.content = '!продать Кость'
        await bot.cmd_sell(ctx)
        ctx.send.assert_called_once()


class TestCmdAppraise(unittest.IsolatedAsyncioTestCase):
    async def test_shows_sell_price(self):
        p = _player(inventory=['Железный меч'])
        bot = _bot({'user': p})
        ctx = _ctx('user', '!оценить Железный меч')
        ctx.message.content = '!оценить Железный меч'
        await bot.cmd_appraise(ctx)
        ctx.send.assert_called_once()
        self.assertIn('40', ctx.send.call_args[0][0])  # 80 // 2 = 40


class TestCmdDescription(unittest.IsolatedAsyncioTestCase):
    async def test_shows_description_by_name(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!описание железный меч')
        ctx.message.content = '!описание железный меч'
        await bot.cmd_description(ctx)
        ctx.send.assert_called_once()
        msg = ctx.send.call_args[0][0]
        self.assertIn('+5-7', msg)

    async def test_unknown_item_sends_error(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!описание несуществующий предмет')
        ctx.message.content = '!описание несуществующий предмет'
        await bot.cmd_description(ctx)
        ctx.send.assert_called_once()


class TestCmdDescriptionExtra(unittest.IsolatedAsyncioTestCase):
    async def test_no_item_arg_no_character(self):
        bot = _bot()
        ctx = _ctx('nobody', '!описание')
        ctx.message.content = '!описание'
        await bot.cmd_description(ctx)
        ctx.send.assert_called_once()
        self.assertIn('нет персонажа', ctx.send.call_args[0][0])

    async def test_single_item_in_inventory_shows_description(self):
        bot = _bot({'user': _player(inventory=['железный меч'])})
        ctx = _ctx('user', '!описание')
        ctx.message.content = '!описание'
        await bot.cmd_description(ctx)
        ctx.send.assert_called_once()

    async def test_multiple_items_shows_list(self):
        bot = _bot({'user': _player(inventory=['железный меч', 'кожаный доспех'])})
        ctx = _ctx('user', '!описание')
        ctx.message.content = '!описание'
        await bot.cmd_description(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('укажи название', msg)

    async def test_empty_inventory_sends_message(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!описание')
        ctx.message.content = '!описание'
        await bot.cmd_description(ctx)
        ctx.send.assert_called_once()


class TestCmdDescriptionNoDesc(unittest.IsolatedAsyncioTestCase):
    async def test_single_item_no_description(self):
        bot = _bot({'user': _player(inventory=['Камень'])})
        ctx = _ctx('user', '!описание')
        ctx.message.content = '!описание'
        await bot.cmd_description(ctx)
        ctx.send.assert_called_once()
        self.assertIn('не найдено', ctx.send.call_args[0][0])


class TestCmdGift(unittest.IsolatedAsyncioTestCase):
    async def test_gift_item_transfers_to_receiver(self):
        sender = _player(inventory=['Деревянный меч'])
        receiver = _player()
        bot = _bot({'alice': sender, 'bob': receiver})
        ctx = _ctx('alice', '!подарить bob Деревянный меч')
        ctx.message.content = '!подарить bob Деревянный меч'
        await bot.cmd_gift(ctx)
        self.assertNotIn('Деревянный меч', bot.players['alice']['inventory'])
        self.assertIn('Деревянный меч', bot.players['bob']['inventory'])

    async def test_gift_gold_transfers_correctly(self):
        sender = _player(gold=500)
        receiver = _player(gold=100)
        bot = _bot({'alice': sender, 'bob': receiver})
        ctx = _ctx('alice', '!подарить bob золото 200')
        ctx.message.content = '!подарить bob золото 200'
        await bot.cmd_gift(ctx)
        self.assertEqual(bot.players['alice']['gold'], 300)
        self.assertEqual(bot.players['bob']['gold'], 300)

    async def test_gift_more_gold_than_owned(self):
        sender = _player(gold=50)
        receiver = _player(gold=0)
        bot = _bot({'alice': sender, 'bob': receiver})
        ctx = _ctx('alice', '!подарить bob золото 200')
        ctx.message.content = '!подарить bob золото 200'
        await bot.cmd_gift(ctx)
        self.assertEqual(bot.players['alice']['gold'], 50)
        self.assertEqual(bot.players['bob']['gold'], 0)


class TestCmdGiftNoChar(unittest.IsolatedAsyncioTestCase):
    async def test_gift_no_character(self):
        bot = _bot()
        ctx = _ctx('nobody', '!подарить bob Меч')
        ctx.message.content = '!подарить bob Меч'
        await bot.cmd_gift(ctx)
        ctx.send.assert_called_once()
        self.assertIn('нет персонажа', ctx.send.call_args[0][0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
