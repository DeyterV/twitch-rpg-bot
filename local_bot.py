"""
Локальный консольный режим RPG-бота.

Запуск:
    MODE=local python rpg_bot.py

Используется, когда нужно тестировать игровую логику без подключения к Twitch.
"""

import asyncio
from types import SimpleNamespace
from typing import Protocol, runtime_checkable

from rpg_bot import RPGbot, PlayerService, CombatService, InventoryService
from rpg_bot import _CLASSES, ITEMS, _RACES, SAVE_FILE


# ---------------------------------------------------------------------------
# Интерфейс контекста
# ---------------------------------------------------------------------------

class _Author(Protocol):
    name: str


class _Message(Protocol):
    content: str


@runtime_checkable
class BotContext(Protocol):
    """Протокол, которому должен удовлетворять объект ctx в командах бота.

    Twitchio Context и LocalContext неявно реализуют этот протокол.
    """

    author: _Author
    message: _Message

    async def send(self, text: str) -> None:
        ...


# ---------------------------------------------------------------------------
# Реализация контекста для консоли
# ---------------------------------------------------------------------------

class LocalContext:
    """Мок twitchio-контекста для консольного режима."""

    def __init__(self, username: str, content: str) -> None:
        self.author = SimpleNamespace(name=username)
        self.message = SimpleNamespace(content=content)

    async def send(self, text: str) -> None:
        print(text)


# ---------------------------------------------------------------------------
# Маппинг команд
# ---------------------------------------------------------------------------

_COMMANDS: dict[str, str] = {
    '!черныйрынок': 'cmd_black_market',
    '!купить':      'cmd_buy',
    '!старт':       'cmd_start',
    '!статус':      'cmd_status',
    '!инвентарь':   'cmd_inventory',
    '!экипировка':  'cmd_equipment',
    '!опыт':        'cmd_xp',
    '!надеть':      'cmd_equip',
    '!снять':       'cmd_unequip',
    '!использовать':'cmd_use',
    '!бой':         'cmd_fight',
    '!топ':         'cmd_top',
    '!дуэль':       'cmd_duel',
    '!принять':     'cmd_accept',
    '!отмена':      'cmd_cancel_duel',
    '!пвп':         'cmd_pvp_stats',
    '!описание':    'cmd_description',
    '!бордель':     'cmd_brothel',
    '!лечиться':    'cmd_heal',
    '!продать':     'cmd_sell',
    '!оценить':     'cmd_appraise',
    '!кража':       'cmd_steal',
    '!взятка':      'cmd_prison',
    '!таверна':     'cmd_tavern',
    '!раса':        'cmd_race',
    '!класс':       'cmd_class',
    '!отдых':       'cmd_full_heal',
    '!подарить':    'cmd_gift',
    '!команды':     'cmd_commands',
    '!милостыня':   'cmd_alms',
}

_HELP = 'Доступные команды: ' + ', '.join(sorted(_COMMANDS))


# ---------------------------------------------------------------------------
# Локальный бот
# ---------------------------------------------------------------------------

class LocalBot(RPGbot):
    """RPG-бот в консольном режиме. Не подключается к Twitch."""

    def __init__(self) -> None:
        # Инициализируем сервисы напрямую, без вызова commands.Bot.__init__
        self.player_service = PlayerService(_CLASSES, ITEMS)
        self.combat_service = CombatService()
        self.inventory_service = InventoryService()
        self.player_service.players = self.load_players()
        self.black_market_items = []
        self.black_market_last_refresh = 0
        self.pending_duels = {}
        self.races = _RACES
        self.classes = _CLASSES

    def run(self) -> None:
        asyncio.run(self._repl())

    async def _repl(self) -> None:
        username = input('Имя игрока [local_user]: ').strip() or 'local_user'
        print(f'Режим: консоль. Игрок: {username}')
        print('Введи !старт чтобы создать персонажа, exit — для выхода.')
        print(_HELP)
        print()

        while True:
            try:
                line = input('> ').strip()
            except (EOFError, KeyboardInterrupt):
                print('\nВыход.')
                self.save_players()
                break

            if line.lower() in ('exit', 'quit', 'выход'):
                self.save_players()
                break

            if not line:
                continue

            ctx = LocalContext(username, line)
            await self._dispatch(ctx)

    async def _dispatch(self, ctx: LocalContext) -> None:
        word = ctx.message.content.split()[0].lower()
        method_name = _COMMANDS.get(word)
        if method_name is None:
            print(f'Неизвестная команда: {word}')
            print(_HELP)
            return
        # @commands.command оборачивает методы в twitchio Command-объект.
        # Получаем исходную функцию через _callback и вызываем её напрямую.
        command_obj = getattr(type(self), method_name)
        callback = getattr(command_obj, '_callback', command_obj)
        await callback(self, ctx)
