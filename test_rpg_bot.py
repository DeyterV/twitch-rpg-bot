"""
Unit tests for twitch-rpg-bot (old version: settings.py + consts.py).

Стратегия:
  - До импорта rpg_bot подменяем sys.modules для settings, filelock, twitchio
    чтобы исключить реальное подключение к Twitch и запись файлов.
  - Для каждого теста создаём свежий экземпляр RPGbot через object.__new__
    (минуя __init__ и super().__init__) и вручную заполняем нужные атрибуты.
  - Метод save_players в тестовых экземплярах заменяется на MagicMock.
"""

import os
import sys
import types
import json
import time
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch, mock_open

# ============================================================
# Подмена внешних зависимостей ДО импорта rpg_bot
# ============================================================

# Переменные окружения вместо settings.py
os.environ['TOKEN'] = 'fake_token'
os.environ['CHANNEL'] = 'test_channel'
os.environ['SAVE_FILE'] = '__nonexistent_players_test__.json'

# dotenv — no-op, чтобы не перезаписать тестовые переменные из реального .env
_dotenv_mod = types.ModuleType('dotenv')
_dotenv_mod.load_dotenv = lambda *a, **kw: None
sys.modules['dotenv'] = _dotenv_mod

# filelock
class _MockFileLock:
    def __init__(self, path): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass

_filelock_mod = types.ModuleType('filelock')
_filelock_mod.FileLock = _MockFileLock
sys.modules['filelock'] = _filelock_mod

# twitchio
def _mock_command(*args, **kwargs):
    return lambda f: f

class _MockCommandsBot:
    def __init__(self, *a, **kw): pass
    def run(self): pass

_twitchio_commands = types.ModuleType('twitchio.ext.commands')
_twitchio_commands.Bot = _MockCommandsBot
_twitchio_commands.command = _mock_command

_twitchio_ext = types.ModuleType('twitchio.ext')
_twitchio_ext.commands = _twitchio_commands

_twitchio = types.ModuleType('twitchio')
_twitchio.ext = _twitchio_ext

sys.modules['twitchio'] = _twitchio
sys.modules['twitchio.ext'] = _twitchio_ext
sys.modules['twitchio.ext.commands'] = _twitchio_commands

# ============================================================
# Импорт основного модуля
# ============================================================
import rpg_bot as rb  # module-level: bot=RPGbot(); bot.run() — оба вызовы безвредны

# ============================================================
# Вспомогательные функции
# ============================================================

def _ctx(username='user', content=''):
    """Создать мок Twitch-контекста."""
    ctx = MagicMock()
    ctx.author.name = username
    ctx.message.content = content
    ctx.send = AsyncMock()
    return ctx


def _player(**kwargs):
    """Создать словарь игрока с дефолтными значениями."""
    p = {
        'level': 1,
        'xp': 0,
        'gold': 100,
        'inventory': [],
        'equipment': {s: None for s in ('weapon', 'armor', 'helmet', 'pet', 'amulet')},
        'last_xp_time': 0,
        'last_fight_time': 0,
        'last_pvp_time': 0,
        'pvp_wins': 0,
        'pvp_losses': 0,
        'prison': False,
        'prison_until': 0,
        'race': None,
        'class': None,
        'current_hp': rb.calculate_hp(1),
    }
    p.update(kwargs)
    return p


def _bot(players=None):
    """
    Создать экземпляр RPGbot минуя __init__ и реальное подключение.
    save_players заменён на MagicMock — файлы не пишутся.
    """
    bot = object.__new__(rb.RPGbot)
    bot.players = players if players is not None else {}
    bot.black_market_items = []
    bot.black_market_last_refresh = 0
    bot.pending_duels = {}
    bot.races = {
        'человек': {'hp_bonus': 5, 'xp_bonus': 0},
        'эльф':    {'hp_bonus': 0, 'xp_bonus': 0.1},
        'орк':     {'hp_bonus': 10, 'xp_bonus': -0.05},
    }
    bot.classes = {
        'воин': {'attack_bonus': (2, 5), 'hp_bonus': 10},
        'маг':  {'attack_bonus': (0, 3), 'xp_bonus': 0.1},
        'вор':  {'attack_bonus': (1, 4), 'steal_chance_bonus': 0.05},
    }
    bot.save_players = MagicMock()
    return bot


# ============================================================
# Тесты чистых функций
# ============================================================

class TestCalculateHp(unittest.TestCase):
    def test_level_1(self):
        self.assertEqual(rb.calculate_hp(1), 30)

    def test_level_5(self):
        self.assertEqual(rb.calculate_hp(5), 50)

    def test_level_10(self):
        self.assertEqual(rb.calculate_hp(10), 75)

    def test_formula_for_all_levels(self):
        for lvl in range(1, 21):
            self.assertEqual(rb.calculate_hp(lvl), 30 + (lvl - 1) * 5)


class TestCalculateDamage(unittest.TestCase):
    def test_level_1_within_range(self):
        for _ in range(100):
            dmg = rb.calculate_damage(1)
            self.assertGreaterEqual(dmg, 7)   # 5 + 1*2
            self.assertLessEqual(dmg, 13)     # 10 + 1*3

    def test_level_10_within_range(self):
        for _ in range(100):
            dmg = rb.calculate_damage(10)
            self.assertGreaterEqual(dmg, 25)  # 5 + 10*2
            self.assertLessEqual(dmg, 40)     # 10 + 10*3

    def test_returns_int(self):
        self.assertIsInstance(rb.calculate_damage(3), int)


# ============================================================
# Тесты try_level_up
# ============================================================

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


# ============================================================
# Тесты get_equipment_bonuses
# ============================================================

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


# ============================================================
# Тесты check_cooldown
# ============================================================

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
        p = _player(last_xp_time=time.time())  # только что
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


# ============================================================
# Тесты load_players
# ============================================================

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
        # Данные старой версии без новых полей
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


# ============================================================
# Тесты refresh_black_market
# ============================================================

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


# ============================================================
# Команда !старт
# ============================================================

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


# ============================================================
# Команда !статус
# ============================================================

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


# ============================================================
# Команда !опыт
# ============================================================

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


# ============================================================
# Команды !надеть / !снять
# ============================================================

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


# ============================================================
# Команда !использовать
# ============================================================

class TestCmdUse(unittest.IsolatedAsyncioTestCase):
    async def test_healing_potion_restores_hp(self):
        p = _player(inventory=['Зелье лечения'], current_hp=5)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!использовать Зелье лечения')
        ctx.message.content = '!использовать Зелье лечения'
        await bot.cmd_use(ctx)
        # min(5+20, 30) = 25
        self.assertEqual(bot.players['user']['current_hp'], 25)
        self.assertNotIn('Зелье лечения', bot.players['user']['inventory'])

    async def test_healing_potion_capped_at_max_hp(self):
        p = _player(inventory=['Зелье лечения'], current_hp=25)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!использовать Зелье лечения')
        ctx.message.content = '!использовать Зелье лечения'
        await bot.cmd_use(ctx)
        self.assertEqual(bot.players['user']['current_hp'], rb.calculate_hp(1))  # 30

    async def test_use_non_consumable_sends_error(self):
        p = _player(inventory=['Железный меч'])
        bot = _bot({'user': p})
        ctx = _ctx('user', '!использовать Железный меч')
        ctx.message.content = '!использовать Железный меч'
        await bot.cmd_use(ctx)
        ctx.send.assert_called_once()
        self.assertIn('Железный меч', bot.players['user']['inventory'])


# ============================================================
# Команда !бой
# ============================================================

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
        with patch('rpg_bot.calculate_damage', return_value=10000):
            await bot.cmd_fight(ctx)
        self.assertGreater(bot.players['user']['xp'], 0)
        self.assertGreater(bot.players['user']['gold'], 0)
        bot.save_players.assert_called()

    async def test_guaranteed_loss_reduces_xp(self):
        p = _player(xp=500, current_hp=1)  # 1 HP — погибнет за 1 удар монстра
        bot = _bot({'user': p})
        ctx = _ctx('user', '!бой Гоблин')
        ctx.message.content = '!бой Гоблин'
        with patch('rpg_bot.calculate_damage', return_value=0):
            await bot.cmd_fight(ctx)
        # 10% XP потеря: 500 - 50 = 450
        self.assertEqual(bot.players['user']['xp'], 450)

    async def test_no_character_sends_message(self):
        bot = _bot()
        ctx = _ctx('nobody', '!бой')
        await bot.cmd_fight(ctx)
        ctx.send.assert_called_once()


# ============================================================
# Команда !топ
# ============================================================

class TestCmdTop(unittest.IsolatedAsyncioTestCase):
    async def test_shows_top_players_sorted(self):
        players = {f'p{i}': _player(level=i) for i in range(1, 6)}
        bot = _bot(players)
        ctx = _ctx('p1', '!топ')
        await bot.cmd_top(ctx)
        ctx.send.assert_called_once()
        msg = ctx.send.call_args[0][0]
        self.assertIn('p5', msg)  # highest level appears first

    async def test_empty_players_sends_message(self):
        bot = _bot()
        ctx = _ctx('user', '!топ')
        await bot.cmd_top(ctx)
        ctx.send.assert_called_once()


# ============================================================
# Команда !инвентарь / !экипировка
# ============================================================

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


# ============================================================
# Команды !продать / !оценить
# ============================================================

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
        p = _player(inventory=['Кость'])  # нет в ITEMS
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


# ============================================================
# Команда !кража
# ============================================================

class TestCmdSteal(unittest.IsolatedAsyncioTestCase):
    async def test_successful_steal_transfers_item(self):
        thief = _player()
        victim = _player(inventory=['Деревянный меч'])
        bot = _bot({'thief': thief, 'victim': victim})
        ctx = _ctx('thief', '!кража @victim Деревянный меч')
        ctx.message.content = '!кража @victim Деревянный меч'
        with patch('random.random', return_value=0.0):  # 0.0 < steal_chance → успех
            await bot.cmd_steal(ctx)
        self.assertIn('Деревянный меч', bot.players['thief']['inventory'])
        self.assertNotIn('Деревянный меч', bot.players['victim']['inventory'])

    async def test_failed_steal_sends_to_prison(self):
        thief = _player()
        victim = _player(inventory=['Деревянный меч'])
        bot = _bot({'thief': thief, 'victim': victim})
        ctx = _ctx('thief', '!кража @victim Деревянный меч')
        ctx.message.content = '!кража @victim Деревянный меч'
        with patch('random.random', return_value=0.99):  # 0.99 > steal_chance → провал
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
        # Инвентарь не изменился — предмет не украден и не задублирован
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
        # Вор без амулета: шанс 0.1+0.05=0.15; с амулетом: +0.05=0.20
        thief = _player(**{'class': 'вор'})
        thief['equipment']['amulet'] = 'Амулет удачи'
        victim = _player(inventory=['Железный меч'])
        bot = _bot({'thief': thief, 'victim': victim})
        ctx = _ctx('thief', '!кража @victim Железный меч')
        ctx.message.content = '!кража @victim Железный меч'
        # random.random() = 0.19 — успех при шансе 0.20, провал при 0.15
        with patch('random.random', return_value=0.19):
            await bot.cmd_steal(ctx)
        self.assertIn('Железный меч', bot.players['thief']['inventory'])


# ============================================================
# Команда !взятка
# ============================================================

class TestCmdPrison(unittest.IsolatedAsyncioTestCase):
    async def test_bribe_frees_from_prison(self):
        p = _player(gold=200, prison=True, prison_until=time.time() + 300)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!взятка')
        await bot.cmd_prison(ctx)
        self.assertFalse(bot.players['user']['prison'])
        self.assertEqual(bot.players['user']['gold'], 150)  # -50

    async def test_bribe_when_not_in_prison_sends_error(self):
        p = _player(gold=200, prison=False)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!взятка')
        await bot.cmd_prison(ctx)
        self.assertEqual(bot.players['user']['gold'], 200)  # не списано
        ctx.send.assert_called_once()

    async def test_bribe_not_enough_gold(self):
        p = _player(gold=10, prison=True, prison_until=time.time() + 300)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!взятка')
        await bot.cmd_prison(ctx)
        self.assertTrue(bot.players['user']['prison'])  # всё ещё в тюрьме


# ============================================================
# Команда !таверна
# ============================================================

class TestCmdTavern(unittest.IsolatedAsyncioTestCase):
    async def test_tavern_grants_attack_buff(self):
        p = _player(gold=200)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!таверна')
        await bot.cmd_tavern(ctx)
        self.assertEqual(bot.players['user']['gold'], 150)  # -50
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
        self.assertEqual(bot.players['user']['gold'], 200)  # не списано


# ============================================================
# Команда !бордель
# ============================================================

class TestCmdBrothel(unittest.IsolatedAsyncioTestCase):
    async def test_brothel_grants_xp_buff(self):
        p = _player(gold=200)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!бордель')
        with patch('random.random', return_value=0.5):  # 0.5 > 0.25 → бафф
            await bot.cmd_brothel(ctx)
        self.assertEqual(bot.players['user']['gold'], 100)  # -100
        self.assertGreater(bot.players['user'].get('xp_buff_until', 0), time.time())

    async def test_brothel_gives_penalty(self):
        p = _player(gold=200)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!бордель')
        with patch('random.random', return_value=0.1):  # 0.1 < 0.25 → штраф
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
        self.assertEqual(bot.players['user']['gold'], 500)  # не списано


# ============================================================
# Команда !лечиться
# ============================================================

class TestCmdHeal(unittest.IsolatedAsyncioTestCase):
    async def test_heal_removes_xp_penalty(self):
        p = _player(gold=200, xp_penalty=True)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!лечиться')
        await bot.cmd_heal(ctx)
        self.assertFalse(bot.players['user']['xp_penalty'])
        self.assertEqual(bot.players['user']['gold'], 150)  # -50

    async def test_heal_without_penalty_sends_error(self):
        p = _player(gold=200)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!лечиться')
        await bot.cmd_heal(ctx)
        self.assertEqual(bot.players['user']['gold'], 200)  # не списано


# ============================================================
# Команды !раса / !класс
# ============================================================

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
        # Орк: +10 hp, но get_equipment_bonuses включает бонус класса (нет) → hp_bonus=0
        expected = rb.calculate_hp(1) + 0  # расы не дают HP через get_equipment_bonuses
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
        # Воин даёт +10 hp через get_equipment_bonuses
        expected = rb.calculate_hp(1) + 10
        self.assertEqual(bot.players['user']['current_hp'], expected)


# ============================================================
# Команда !отдых
# ============================================================

class TestCmdFullHeal(unittest.IsolatedAsyncioTestCase):
    async def test_restores_hp(self):
        p = _player(gold=100, current_hp=10)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!отдых')
        await bot.cmd_full_heal(ctx)
        self.assertEqual(bot.players['user']['current_hp'], rb.calculate_hp(1))
        self.assertEqual(bot.players['user']['gold'], 95)  # -5

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
        self.assertEqual(bot.players['user']['current_hp'], 10)  # не восстановлено


# ============================================================
# Команда !подарить
# ============================================================

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
        self.assertEqual(bot.players['alice']['gold'], 50)   # не изменилось
        self.assertEqual(bot.players['bob']['gold'], 0)


# ============================================================
# Команда !пвп
# ============================================================

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


# ============================================================
# Команды !дуэль / !принять / !отмена
# ============================================================

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
        bot = _bot({'alice': _player()})  # bob не существует
        ctx = _ctx('alice', '!дуэль @bob')
        ctx.message.content = '!дуэль @bob'
        await bot.cmd_duel(ctx)
        self.assertNotIn('bob', bot.pending_duels)


class TestCmdAccept(unittest.IsolatedAsyncioTestCase):
    async def test_duel_completes_and_gold_conserved(self):
        alice = _player(level=5, gold=100)
        bob = _player(level=5, gold=100)
        bot = _bot({'alice': alice, 'bob': bob})
        bot.pending_duels['bob'] = {'challenger': 'alice', 'amount': 50}
        ctx = _ctx('bob', '!принять')
        await bot.cmd_accept(ctx)
        self.assertNotIn('bob', bot.pending_duels)
        # Оба заплатили по 50, победитель получил 100 назад
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
        # Победитель получает 10 * level_проигравшего = 30
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


# ============================================================
# Команда !черныйрынок / !купить
# ============================================================

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
        bot.black_market_last_refresh = 0  # никогда не обновлялся
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


# ============================================================
# Команда !описание
# ============================================================

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


# ============================================================
# save_players (lines 99-111)
# ============================================================

class TestSavePlayers(unittest.TestCase):
    def _real_bot(self, players):
        bot = object.__new__(rb.RPGbot)
        bot.players = players
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


# ============================================================
# event_ready (lines 167-168)
# ============================================================

class TestEventReady(unittest.IsolatedAsyncioTestCase):
    async def test_event_ready_runs_without_error(self):
        bot = object.__new__(rb.RPGbot)
        bot.nick = 'testbot'
        await rb.RPGbot.event_ready(bot)  # should not raise


# ============================================================
# cmd_buy — bad format / else branch (lines 195-196, 219)
# ============================================================

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
        # item type not in ['pet', 'amulet', 'consumable'] → else branch (line 219)
        bot = _bot({'user': _player(gold=1000)})
        bot.black_market_items = [{'name': 'Особый меч', 'type': 'weapon', 'price': 50, 'description': ''}]
        bot.black_market_last_refresh = time.time()
        ctx = _ctx('user', '!купить 1')
        ctx.message.content = '!купить 1'
        await bot.cmd_buy(ctx)
        self.assertIn('Особый меч', bot.players['user']['inventory'])
        msg = ctx.send.call_args[0][0]
        self.assertIn('Особый меч', msg)


# ============================================================
# cmd_status — race/class and buffs (lines 272, 274, 280, 282, 287-288)
# ============================================================

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


# ============================================================
# cmd_equipment / cmd_equip / cmd_unequip / cmd_use — no character guards
# ============================================================

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


# ============================================================
# cmd_fight — win with drop and level-up (lines 519, 527, 530)
# ============================================================

class TestCmdFightExtra(unittest.IsolatedAsyncioTestCase):
    async def test_fight_win_with_drop(self):
        p = _player(level=1, xp=0, gold=100)
        bot = _bot({'user': p})
        ctx = _ctx('user', '!бой')
        # First random.choice → monster name, second → drop item
        choice_values = iter(['Гоблин', 'Деревянный меч'])
        with patch('rpg_bot.calculate_damage', return_value=10000), \
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
        # Choose a monster via choice, random.random > loot_chance → no drop
        with patch('rpg_bot.calculate_damage', return_value=10000), \
             patch('random.random', return_value=0.99), \
             patch('random.choice', side_effect=lambda seq: list(seq)[0] if hasattr(seq, '__len__') else seq), \
             patch('random.randint', return_value=5):
            await bot.cmd_fight(ctx)
        # Player should have leveled up (xp was 95 + at least 5 = 100)
        all_text = ' '.join(c[0][0] for c in ctx.send.call_args_list)
        self.assertIn('Уровень повышен', all_text)


# ============================================================
# cmd_duel — missing branches (lines 559-560, 578-579)
# ============================================================

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
        # alice's duel shouldn't overwrite charlie's
        self.assertEqual(bot.pending_duels['bob']['challenger'], 'charlie')
        msg = ctx.send.call_args[0][0]
        self.assertIn('уже ожидает', msg)


# ============================================================
# cmd_accept — missing branches (601-602, 606-608, 619-620, 625, 628-629, 693)
# ============================================================

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
        alice = _player(level=5, gold=0, xp=480)  # needs 10*5=50 xp to levelup at level 5 (500 total)
        bob = _player(level=5, gold=0, xp=0)
        bot = _bot({'alice': alice, 'bob': bob})
        bot.pending_duels['bob'] = {'challenger': 'alice', 'amount': 0}
        ctx = _ctx('bob', '!принять')
        with patch('rpg_bot.calculate_damage', return_value=10000):
            with patch('random.random', return_value=0.0):  # alice goes first → wins
                await bot.cmd_accept(ctx)
        all_text = ' '.join(c[0][0] for c in ctx.send.call_args_list)
        # Either winner leveled up or the message was sent - check level increased
        total_level = bot.players['alice']['level'] + bot.players['bob']['level']
        self.assertGreater(total_level, 10)  # one of them leveled


# ============================================================
# cmd_pvp_stats — no character (lines 718-719)
# ============================================================

class TestCmdPvpStatsExtra(unittest.IsolatedAsyncioTestCase):
    async def test_no_character_sends_error(self):
        bot = _bot()
        ctx = _ctx('nobody', '!пвп')
        await bot.cmd_pvp_stats(ctx)
        ctx.send.assert_called_once()
        self.assertIn('нет персонажа', ctx.send.call_args[0][0])


# ============================================================
# cmd_description — no character, single item, multiple items (742-760)
# ============================================================

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


# ============================================================
# "No character" guards for remaining commands
# ============================================================

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


# ============================================================
# ImportError handler in rpg_bot.py (lines 18-20)
# ============================================================

class TestImportErrorHandler(unittest.TestCase):
    def test_import_error_triggers_handler(self):
        import importlib

        saved_rpg = sys.modules.get('rpg_bot')
        saved_consts = sys.modules.get('consts')

        # Broken consts: missing MONSTERS, ITEMS, etc.
        broken_consts = types.ModuleType('consts')
        sys.modules['consts'] = broken_consts
        sys.modules.pop('rpg_bot', None)

        try:
            with self.assertRaises(ImportError):
                importlib.import_module('rpg_bot')
        finally:
            sys.modules['consts'] = saved_consts
            sys.modules['rpg_bot'] = saved_rpg


# ============================================================
# cmd_inventory / cmd_equipment — no character (lines 297-298, 314-315)
# ============================================================

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


# ============================================================
# cmd_accept — pvp cooldown (line 625) and defender wins (668-670)
# ============================================================

class TestCmdAcceptCooldownAndDefenderWin(unittest.IsolatedAsyncioTestCase):
    async def test_pvp_cooldown_blocks_duel(self):
        alice = _player(last_pvp_time=time.time(), gold=0)  # on cooldown
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
        # alice = attacker (random < 0.5), alice hits 0 damage, bob kills alice
        dmg_iter = iter([0, 10000])
        with patch('rpg_bot.calculate_damage', side_effect=lambda lvl: next(dmg_iter)), \
             patch('random.random', return_value=0.0), \
             patch('random.randint', return_value=0):
            await bot.cmd_accept(ctx)
        all_text = ' '.join(c[0][0] for c in ctx.send.call_args_list)
        self.assertIn('bob', all_text)


# ============================================================
# cmd_description — single item with no description (line 758)
# ============================================================

class TestCmdDescriptionNoDesc(unittest.IsolatedAsyncioTestCase):
    async def test_single_item_no_description(self):
        # 'Камень' doesn't exist in ITEM_DESCRIPTIONS
        bot = _bot({'user': _player(inventory=['Камень'])})
        ctx = _ctx('user', '!описание')
        ctx.message.content = '!описание'
        await bot.cmd_description(ctx)
        ctx.send.assert_called_once()
        self.assertIn('не найдено', ctx.send.call_args[0][0])


# ============================================================
# cmd_heal — has penalty but no gold (lines 812-813)
# ============================================================

class TestCmdHealNoGold(unittest.IsolatedAsyncioTestCase):
    async def test_heal_with_penalty_but_no_gold(self):
        p = _player(gold=10, xp_penalty=True)  # cost is 50
        bot = _bot({'user': p})
        ctx = _ctx('user', '!лечиться')
        await bot.cmd_heal(ctx)
        self.assertTrue(bot.players['user']['xp_penalty'])  # still penalised
        self.assertIn('недостаточно золота', ctx.send.call_args[0][0])


# ============================================================
# cmd_steal — cooldown (line 907)
# ============================================================

class TestCmdStealCooldown(unittest.IsolatedAsyncioTestCase):
    async def test_steal_blocked_by_cooldown(self):
        thief = _player(steal_time_unteal=time.time())  # fresh cooldown
        victim = _player(inventory=['Деревянный меч'])
        bot = _bot({'user': thief, 'victim': victim})
        ctx = _ctx('user', '!кража @victim Деревянный меч')
        ctx.message.content = '!кража @victim Деревянный меч'
        await bot.cmd_steal(ctx)
        self.assertNotIn('Деревянный меч', bot.players['user']['inventory'])
        ctx.send.assert_called_once()


# ============================================================
# cmd_gift — no character (lines 1079-1080, now reachable after bug fix)
# ============================================================

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
