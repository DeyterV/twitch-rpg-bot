"""Тесты боевых команд: !бой, !дуэль, !принять, !отмена, !пвп."""

import time
import unittest
from unittest.mock import patch

from tests.helpers import _bot, _player, _ctx


class TestCmdFight(unittest.IsolatedAsyncioTestCase):
    async def test_prison_blocks_fight(self):
        p = _player(prison=True, prison_until=time.time() + 300)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!бой')
        await bot.cmd_fight(ctx)
        ctx.send.assert_called_once()
        self.assertIn('тюрьме', ctx.send.call_args[0][0])

    async def test_cooldown_blocks_fight(self):
        p = _player(last_fight_time=time.time())
        bot = _bot({'user': p})
        ctx = _ctx('user', '!бой')
        await bot.cmd_fight(ctx)
        ctx.send.assert_called_once()

    async def test_guaranteed_win_grants_xp_and_gold(self):
        p = _player(xp=0, gold=0)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!бой Гоблин')
        ctx.message.content = '!бой Гоблин'
        with patch('services.combat_service.calculate_damage', return_value=10000):
            await bot.cmd_fight(ctx)
        self.assertGreater(bot.players['user']['xp'], 0)
        self.assertGreater(bot.players['user']['gold'], 0)
        bot.save_players.assert_called()

    async def test_guaranteed_loss_reduces_xp(self):
        p = _player(xp=500, current_hp=1)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!бой Гоблин')
        ctx.message.content = '!бой Гоблин'
        with patch('services.combat_service.calculate_damage', return_value=0):
            await bot.cmd_fight(ctx)
        self.assertEqual(bot.players['user']['xp'], 450)

    async def test_no_character_sends_message(self):
        bot = _bot()
        ctx = _ctx('nobody', '!бой')
        await bot.cmd_fight(ctx)
        ctx.send.assert_called_once()


class TestCmdFightExtra(unittest.IsolatedAsyncioTestCase):
    async def test_fight_win_with_drop(self):
        p = _player(level=1, xp=0, gold=100)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!бой')
        choice_values = iter(['Гоблин', 'Деревянный меч'])
        with patch('services.combat_service.calculate_damage', return_value=10000), \
             patch('random.random', return_value=0.0), \
             patch('random.choice', side_effect=lambda seq: next(choice_values)), \
             patch('random.randint', return_value=10):
            await bot.cmd_fight(ctx)
        all_text = ' '.join(c[0][0] for c in ctx.send.call_args_list)
        self.assertIn('Дроп', all_text)

    async def test_fight_win_with_level_up(self):
        p = _player(level=1, xp=95, gold=100)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!бой')
        with patch('services.combat_service.calculate_damage', return_value=10000), \
             patch('random.random', return_value=0.99), \
             patch('random.choice', side_effect=lambda seq: list(seq)[0] if hasattr(seq, '__len__') else seq), \
             patch('random.randint', return_value=5):
            await bot.cmd_fight(ctx)
        all_text = ' '.join(c[0][0] for c in ctx.send.call_args_list)
        self.assertIn('Уровень повышен', all_text)


class TestCmdDuel(unittest.IsolatedAsyncioTestCase):
    async def test_creates_pending_duel(self):
        challenger = _player(gold=200)
        target = _player()
        bot = _bot({'alice': challenger, 'bob': target})
        ctx = _ctx('alice', '!дуэль @bob 50')
        ctx.message.content = '!дуэль @bob 50'
        await bot.cmd_duel(ctx)
        self.assertIn('bob', bot.pending_duels)
        self.assertEqual(bot.pending_duels['bob']['challenger'], 'alice')
        self.assertEqual(bot.pending_duels['bob']['amount'], 50)

    async def test_duel_self_rejected(self):
        bot = _bot({'alice': _player()})
        ctx = _ctx('alice', '!дуэль @alice')
        ctx.message.content = '!дуэль @alice'
        await bot.cmd_duel(ctx)
        self.assertNotIn('alice', bot.pending_duels)

    async def test_duel_not_enough_gold(self):
        challenger = _player(gold=10)
        bot = _bot({'alice': challenger, 'bob': _player()})
        ctx = _ctx('alice', '!дуэль @bob 100')
        ctx.message.content = '!дуэль @bob 100'
        await bot.cmd_duel(ctx)
        self.assertNotIn('bob', bot.pending_duels)

    async def test_duel_without_characters_rejected(self):
        bot = _bot({'alice': _player()})
        ctx = _ctx('alice', '!дуэль @bob')
        ctx.message.content = '!дуэль @bob'
        await bot.cmd_duel(ctx)
        self.assertNotIn('bob', bot.pending_duels)


class TestCmdDuelExtra(unittest.IsolatedAsyncioTestCase):
    async def test_duel_no_target_sends_format_hint(self):
        bot = _bot({'alice': _player()})
        ctx = _ctx('alice', '!дуэль')
        ctx.message.content = '!дуэль'
        await bot.cmd_duel(ctx)
        ctx.send.assert_called_once()
        self.assertIn('Формат', ctx.send.call_args[0][0])

    async def test_duel_target_already_in_pending(self):
        alice = _player(gold=200)
        bob = _player()
        charlie = _player(gold=100)
        bot = _bot({'alice': alice, 'bob': bob, 'charlie': charlie})
        bot.pending_duels['bob'] = {'challenger': 'charlie', 'amount': 0}
        ctx = _ctx('alice', '!дуэль @bob')
        ctx.message.content = '!дуэль @bob'
        await bot.cmd_duel(ctx)
        self.assertEqual(bot.pending_duels['bob']['challenger'], 'charlie')
        msg = ctx.send.call_args[0][0]
        self.assertIn('уже ожидает', msg)


class TestCmdAccept(unittest.IsolatedAsyncioTestCase):
    async def test_duel_completes_and_gold_conserved(self):
        alice = _player(level=5, gold=100)
        bob = _player(level=5, gold=100)
        bot = _bot({'alice': alice, 'bob': bob})
        bot.pending_duels['bob'] = {'challenger': 'alice', 'amount': 50}
        ctx = _ctx('bob', '!принять')
        await bot.cmd_accept(ctx)
        self.assertNotIn('bob', bot.pending_duels)
        total = bot.players['alice']['gold'] + bot.players['bob']['gold']
        self.assertEqual(total, 200)

    async def test_winner_gets_xp(self):
        alice = _player(level=3, gold=0, xp=0)
        bob = _player(level=3, gold=0, xp=0)
        bot = _bot({'alice': alice, 'bob': bob})
        bot.pending_duels['bob'] = {'challenger': 'alice', 'amount': 0}
        ctx = _ctx('bob', '!принять')
        await bot.cmd_accept(ctx)
        total_xp = bot.players['alice']['xp'] + bot.players['bob']['xp']
        self.assertEqual(total_xp, 30)

    async def test_accept_without_pending_duel_sends_error(self):
        bot = _bot({'bob': _player()})
        ctx = _ctx('bob', '!принять')
        await bot.cmd_accept(ctx)
        ctx.send.assert_called_once()

    async def test_pvp_stats_updated_after_duel(self):
        alice = _player(level=1, gold=0)
        bob = _player(level=1, gold=0)
        bot = _bot({'alice': alice, 'bob': bob})
        bot.pending_duels['bob'] = {'challenger': 'alice', 'amount': 0}
        ctx = _ctx('bob', '!принять')
        await bot.cmd_accept(ctx)
        total_wins = bot.players['alice']['pvp_wins'] + bot.players['bob']['pvp_wins']
        total_losses = bot.players['alice']['pvp_losses'] + bot.players['bob']['pvp_losses']
        self.assertEqual(total_wins, 1)
        self.assertEqual(total_losses, 1)


class TestCmdAcceptExtra(unittest.IsolatedAsyncioTestCase):
    async def test_accept_no_character(self):
        bot = _bot()
        ctx = _ctx('nobody', '!принять')
        await bot.cmd_accept(ctx)
        ctx.send.assert_called_once()

    async def test_accept_while_in_prison(self):
        p = _player(prison=True, prison_until=time.time() + 300)
        bot = _bot({'user': p})
        bot.pending_duels['user'] = {'challenger': 'alice', 'amount': 0}
        ctx = _ctx('user', '!принять')
        await bot.cmd_accept(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('тюрьм', msg)

    async def test_accept_challenger_not_found(self):
        bot = _bot({'bob': _player()})
        bot.pending_duels['bob'] = {'challenger': 'ghost', 'amount': 0}
        ctx = _ctx('bob', '!принять')
        await bot.cmd_accept(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('не найден', msg)

    async def test_accept_not_enough_gold_for_bet(self):
        alice = _player(gold=10)
        bob = _player(gold=10)
        bot = _bot({'alice': alice, 'bob': bob})
        bot.pending_duels['bob'] = {'challenger': 'alice', 'amount': 50}
        ctx = _ctx('bob', '!принять')
        await bot.cmd_accept(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('не хватает золота', msg)

    async def test_accept_duel_with_level_up(self):
        alice = _player(level=5, gold=0, xp=480)
        bob = _player(level=5, gold=0, xp=0)
        bot = _bot({'alice': alice, 'bob': bob})
        bot.pending_duels['bob'] = {'challenger': 'alice', 'amount': 0}
        ctx = _ctx('bob', '!принять')
        with patch('services.combat_service.calculate_damage', return_value=10000):
            with patch('random.random', return_value=0.0):
                await bot.cmd_accept(ctx)
        total_level = bot.players['alice']['level'] + bot.players['bob']['level']
        self.assertGreater(total_level, 10)


class TestCmdAcceptCooldownAndDefenderWin(unittest.IsolatedAsyncioTestCase):
    async def test_pvp_cooldown_blocks_duel(self):
        alice = _player(last_pvp_time=time.time(), gold=0)
        bob = _player(gold=0)
        bot = _bot({'alice': alice, 'bob': bob})
        bot.pending_duels['bob'] = {'challenger': 'alice', 'amount': 0}
        ctx = _ctx('bob', '!принять')
        await bot.cmd_accept(ctx)
        ctx.send.assert_called_once()
        self.assertIn('подожди', ctx.send.call_args[0][0])

    async def test_defender_wins_duel(self):
        alice = _player(level=5, gold=0, xp=0)
        bob = _player(level=5, gold=0, xp=0)
        bot = _bot({'alice': alice, 'bob': bob})
        bot.pending_duels['bob'] = {'challenger': 'alice', 'amount': 0}
        ctx = _ctx('bob', '!принять')
        dmg_iter = iter([0, 10000])
        with patch('services.combat_service.calculate_damage', side_effect=lambda lvl: next(dmg_iter)), \
             patch('random.random', return_value=0.0), \
             patch('random.randint', return_value=0):
            await bot.cmd_accept(ctx)
        all_text = ' '.join(c[0][0] for c in ctx.send.call_args_list)
        self.assertIn('bob', all_text)


class TestCmdCancelDuel(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_outgoing_challenge(self):
        alice = _player()
        bob = _player()
        bot = _bot({'alice': alice, 'bob': bob})
        bot.pending_duels['bob'] = {'challenger': 'alice', 'amount': 0}
        ctx = _ctx('alice', '!отмена')
        await bot.cmd_cancel_duel(ctx)
        self.assertNotIn('bob', bot.pending_duels)

    async def test_cancel_incoming_challenge(self):
        alice = _player()
        bob = _player()
        bot = _bot({'alice': alice, 'bob': bob})
        bot.pending_duels['alice'] = {'challenger': 'bob', 'amount': 0}
        ctx = _ctx('alice', '!отмена')
        await bot.cmd_cancel_duel(ctx)
        self.assertNotIn('alice', bot.pending_duels)

    async def test_cancel_no_duel_sends_message(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!отмена')
        await bot.cmd_cancel_duel(ctx)
        ctx.send.assert_called_once()


class TestCmdPvpStats(unittest.IsolatedAsyncioTestCase):
    async def test_shows_win_loss_stats(self):
        p = _player(pvp_wins=5, pvp_losses=3)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!пвп')
        await bot.cmd_pvp_stats(ctx)
        ctx.send.assert_called_once()
        msg = ctx.send.call_args[0][0]
        self.assertIn('5', msg)
        self.assertIn('3', msg)

    async def test_winrate_shown_correctly(self):
        p = _player(pvp_wins=1, pvp_losses=1)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!пвп')
        await bot.cmd_pvp_stats(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('50.0%', msg)

    async def test_no_games_shows_dash(self):
        bot = _bot({'user': _player()})
        ctx = _ctx('user', '!пвп')
        await bot.cmd_pvp_stats(ctx)
        msg = ctx.send.call_args[0][0]
        self.assertIn('–', msg)


class TestCmdPvpStatsExtra(unittest.IsolatedAsyncioTestCase):
    async def test_no_character_sends_error(self):
        bot = _bot()
        ctx = _ctx('nobody', '!пвп')
        await bot.cmd_pvp_stats(ctx)
        ctx.send.assert_called_once()
        self.assertIn('нет персонажа', ctx.send.call_args[0][0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
