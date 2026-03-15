"""Тесты локального консольного режима: LocalContext, LocalBot, BotContext."""

import unittest
from unittest.mock import patch, MagicMock

from local_bot import BotContext, LocalContext, LocalBot, _COMMANDS
from tests.helpers import _player


class TestLocalContext(unittest.TestCase):
    def setUp(self):
        self.ctx = LocalContext('alice', '!старт')

    def test_author_name(self):
        self.assertEqual(self.ctx.author.name, 'alice')

    def test_message_content(self):
        self.assertEqual(self.ctx.message.content, '!старт')

    def test_implements_bot_context_protocol(self):
        self.assertIsInstance(self.ctx, BotContext)

    def test_send_is_coroutine(self):
        import asyncio
        import inspect
        self.assertTrue(inspect.iscoroutinefunction(self.ctx.send))


class TestLocalBot(unittest.TestCase):
    def _make_bot(self, players=None):
        bot = object.__new__(LocalBot)
        from unittest.mock import MagicMock
        from tests.helpers import _CLASSES, _RACES
        from services.player_service import PlayerService
        from services.combat_service import CombatService
        from services.inventory_service import InventoryService
        import rpg_bot as rb
        ps = object.__new__(PlayerService)
        ps.players = players if players is not None else {}
        ps.classes = _CLASSES
        ps.items = rb.ITEMS
        bot.player_service = ps
        bot.combat_service = CombatService()
        bot.inventory_service = InventoryService()
        bot.black_market_items = []
        bot.black_market_last_refresh = 0
        bot.pending_duels = {}
        bot.races = _RACES
        bot.classes = _CLASSES
        bot.save_players = MagicMock()
        return bot

    def test_all_commands_have_handler(self):
        bot = self._make_bot()
        for cmd, method_name in _COMMANDS.items():
            self.assertTrue(
                hasattr(bot, method_name),
                msg=f'Команда {cmd}: метод {method_name} не найден в LocalBot'
            )

    def test_commands_map_is_complete(self):
        # Убеждаемся, что словарь покрывает все 30 команд
        self.assertEqual(len(_COMMANDS), 30)


class TestLocalBotDispatch(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from unittest.mock import MagicMock, AsyncMock
        from tests.helpers import _CLASSES, _RACES
        from services.player_service import PlayerService
        from services.combat_service import CombatService
        from services.inventory_service import InventoryService
        import rpg_bot as rb

        self.bot = object.__new__(LocalBot)
        ps = object.__new__(PlayerService)
        ps.players = {}
        ps.classes = _CLASSES
        ps.items = rb.ITEMS
        self.bot.player_service = ps
        self.bot.combat_service = CombatService()
        self.bot.inventory_service = InventoryService()
        self.bot.black_market_items = []
        self.bot.black_market_last_refresh = 0
        self.bot.pending_duels = {}
        self.bot.races = _RACES
        self.bot.classes = _CLASSES
        self.bot.save_players = MagicMock()

    async def test_dispatch_calls_correct_handler(self):
        # _dispatch вызывает реальный cmd_start — проверяем по эффекту
        ctx = LocalContext('user', '!старт')
        await self.bot._dispatch(ctx)
        self.assertIn('user', self.bot.players)

    async def test_dispatch_unknown_command_prints_help(self, capsys=None):
        ctx = LocalContext('user', '!несуществует')
        # Should not raise — just prints help
        await self.bot._dispatch(ctx)

    async def test_dispatch_creates_player_via_start(self):
        ctx = LocalContext('newuser', '!старт')
        await self.bot._dispatch(ctx)
        self.assertIn('newuser', self.bot.players)


class TestLocalBotInit(unittest.TestCase):
    def test_init_creates_services(self):
        bot = LocalBot()
        self.assertIsNotNone(bot.player_service)
        self.assertIsNotNone(bot.combat_service)
        self.assertIsNotNone(bot.inventory_service)
        self.assertEqual(bot.players, {})
        self.assertEqual(bot.black_market_items, [])


class TestLocalBotRun(unittest.TestCase):
    def test_run_calls_asyncio_run(self):
        from unittest.mock import MagicMock, patch
        bot = LocalBot()
        bot.save_players = MagicMock()
        with patch('local_bot.asyncio.run') as mock_run:
            bot.run()
        mock_run.assert_called_once()


class TestLocalBotRepl(unittest.IsolatedAsyncioTestCase):
    def _make_bot(self):
        from unittest.mock import MagicMock
        bot = LocalBot()
        bot.save_players = MagicMock()
        return bot

    async def test_repl_exit_command(self):
        bot = self._make_bot()
        with patch('builtins.input', side_effect=['myuser', 'exit']):
            await bot._repl()
        bot.save_players.assert_called_once()

    async def test_repl_quit_command(self):
        bot = self._make_bot()
        with patch('builtins.input', side_effect=['myuser', 'quit']):
            await bot._repl()
        bot.save_players.assert_called_once()

    async def test_repl_russian_exit(self):
        bot = self._make_bot()
        with patch('builtins.input', side_effect=['myuser', 'выход']):
            await bot._repl()
        bot.save_players.assert_called_once()

    async def test_repl_eoferror_exits(self):
        bot = self._make_bot()
        with patch('builtins.input', side_effect=['myuser', EOFError()]):
            await bot._repl()
        bot.save_players.assert_called_once()

    async def test_repl_empty_line_skipped(self):
        bot = self._make_bot()
        with patch('builtins.input', side_effect=['myuser', '', 'exit']):
            await bot._repl()

    async def test_repl_default_username_on_empty_input(self):
        bot = self._make_bot()
        with patch('builtins.input', side_effect=['', 'exit']):
            await bot._repl()

    async def test_repl_valid_command_dispatched(self):
        bot = self._make_bot()
        with patch('builtins.input', side_effect=['myuser', '!старт', 'exit']):
            await bot._repl()
        self.assertIn('myuser', bot.players)

    async def test_repl_unknown_command_does_not_raise(self):
        bot = self._make_bot()
        with patch('builtins.input', side_effect=['myuser', '!несуществует', 'exit']):
            await bot._repl()


if __name__ == '__main__':
    unittest.main(verbosity=2)
