"""Тесты загрузки/сохранения данных, событий и рефреша чёрного рынка."""

import json
import sys
import unittest
from unittest.mock import patch, mock_open

import rpg_bot as rb
from tests.helpers import _bot, _player


class TestLoadPlayers(unittest.TestCase):
    def setUp(self):
        self.bot = _bot()

    def test_nonexistent_file_returns_empty_dict(self):
        with patch('rpg_bot.SAVE_FILE', '__no_such_file_xyz__.json'):
            result = self.bot.load_players()
        self.assertEqual(result, {})

    def test_empty_file_returns_empty_dict(self):
        with patch('rpg_bot.SAVE_FILE', 'x.json'), \
             patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data='   ')):
            result = self.bot.load_players()
        self.assertEqual(result, {})

    def test_valid_json_loaded_correctly(self):
        data = {'alice': _player(level=5, gold=999)}
        with patch('rpg_bot.SAVE_FILE', 'x.json'), \
             patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=json.dumps(data))):
            result = self.bot.load_players()
        self.assertIn('alice', result)
        self.assertEqual(result['alice']['level'], 5)
        self.assertEqual(result['alice']['gold'], 999)

    def test_missing_fields_are_migrated(self):
        data = {'bob': {'level': 2, 'xp': 10, 'gold': 50,
                        'inventory': [],
                        'equipment': {s: None for s in ('weapon', 'armor', 'helmet', 'pet', 'amulet')}}}
        with patch('rpg_bot.SAVE_FILE', 'x.json'), \
             patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=json.dumps(data))):
            result = self.bot.load_players()
        for field in ('prison', 'race', 'class', 'current_hp', 'pvp_wins', 'pvp_losses'):
            self.assertIn(field, result['bob'], msg=f"Missing field: {field}")

    def test_invalid_json_returns_empty_dict(self):
        with patch('rpg_bot.SAVE_FILE', 'x.json'), \
             patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data='{ invalid')):
            result = self.bot.load_players()
        self.assertEqual(result, {})


class TestRefreshBlackMarket(unittest.TestCase):
    def test_updates_timestamp(self):
        bot = _bot()
        before = bot.black_market_last_refresh
        bot.refresh_black_market()
        self.assertGreater(bot.black_market_last_refresh, before)

    def test_items_count_is_1_to_3(self):
        bot = _bot()
        bot.refresh_black_market()
        self.assertGreaterEqual(len(bot.black_market_items), 1)
        self.assertLessEqual(len(bot.black_market_items), 3)

    def test_items_come_from_black_market_list(self):
        bot = _bot()
        bot.refresh_black_market()
        valid = {item['name'] for item in rb.BLACK_MARKET_ITEMS}
        for item in bot.black_market_items:
            self.assertIn(item['name'], valid)


class TestSavePlayers(unittest.TestCase):
    def _real_bot(self, players):
        from services.player_service import PlayerService
        bot = object.__new__(rb.RPGbot)
        ps = object.__new__(PlayerService)
        ps.players = players
        ps.classes = {}
        ps.items = rb.ITEMS
        bot.player_service = ps
        return bot

    def test_saves_data_to_file(self):
        import tempfile, os
        bot = self._real_bot({'hero': {'level': 7, 'gold': 300}})
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            tmp = f.name
        os.unlink(tmp)
        try:
            with patch('rpg_bot.SAVE_FILE', tmp):
                rb.RPGbot.save_players(bot)
            with open(tmp, encoding='utf-8') as f:
                data = json.load(f)
            self.assertEqual(data['hero']['level'], 7)
        finally:
            for p in [tmp, tmp + '.bak', tmp + '.lock']:
                if os.path.exists(p):
                    os.unlink(p)

    def test_creates_backup_of_existing_file(self):
        import tempfile, os
        bot = self._real_bot({'hero': {'level': 2}})
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w', encoding='utf-8') as f:
            json.dump({'hero': {'level': 1}}, f)
            tmp = f.name
        try:
            with patch('rpg_bot.SAVE_FILE', tmp):
                rb.RPGbot.save_players(bot)
            self.assertTrue(os.path.exists(tmp + '.bak'))
        finally:
            for p in [tmp, tmp + '.bak', tmp + '.lock']:
                if os.path.exists(p):
                    os.unlink(p)

    def test_handles_ioerror_gracefully(self):
        bot = self._real_bot({})
        with patch('rpg_bot.SAVE_FILE', '/nonexistent_dir/nope.json'):
            try:
                rb.RPGbot.save_players(bot)
            except Exception:
                self.fail('save_players raised unexpectedly on IOError')


class TestEventReady(unittest.IsolatedAsyncioTestCase):
    async def test_event_ready_runs_without_error(self):
        bot = object.__new__(rb.RPGbot)
        bot.nick = 'testbot'
        await rb.RPGbot.event_ready(bot)


class TestImportErrorHandler(unittest.TestCase):
    def test_missing_consts_yml_raises(self):
        import importlib

        saved_rpg = sys.modules.pop('rpg_bot', None)

        try:
            real_open = open
            def fake_open(path, *a, **kw):
                if 'consts' in str(path) and str(path).endswith('.yml'):
                    raise FileNotFoundError('consts file not found')
                return real_open(path, *a, **kw)

            with patch('builtins.open', side_effect=fake_open):
                with self.assertRaises(FileNotFoundError):
                    importlib.import_module('rpg_bot')
        finally:
            sys.modules['rpg_bot'] = saved_rpg


if __name__ == '__main__':
    unittest.main(verbosity=2)
