"""
Общие вспомогательные функции для тестов.
conftest.py гарантирует подмену внешних зависимостей до первого импорта этого модуля.
"""

from unittest.mock import MagicMock, AsyncMock

import rpg_bot as rb
from services.player_service import PlayerService, calculate_hp
from services.combat_service import CombatService
from services.inventory_service import InventoryService

_CLASSES = {
    'воин': {'attack_bonus': (2, 5), 'hp_bonus': 10},
    'маг':  {'attack_bonus': (0, 3), 'xp_bonus': 0.1},
    'вор':  {'attack_bonus': (1, 4), 'steal_chance_bonus': 0.05},
}

_RACES = {
    'человек': {'hp_bonus': 5, 'xp_bonus': 0},
    'эльф':    {'hp_bonus': 0, 'xp_bonus': 0.1},
    'орк':     {'hp_bonus': 10, 'xp_bonus': -0.05},
}


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
        'current_hp': calculate_hp(1),
    }
    p.update(kwargs)
    return p


def _bot(players=None):
    """
    Создать экземпляр RPGbot минуя __init__ и реальное подключение.
    save_players заменён на MagicMock — файлы не пишутся.
    """
    bot = object.__new__(rb.RPGbot)

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
