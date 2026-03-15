import asyncio
import json
import os
import random
import time
import shutil
import logging
import yaml
from collections import Counter
from dotenv import load_dotenv
from filelock import FileLock
from twitchio.ext import commands

from services.player_service import PlayerService, calculate_hp, calculate_damage
from services.combat_service import CombatService
from services.inventory_service import InventoryService
from utils.decorators import requires_character

# Настройка логирования
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()
TOKEN = os.getenv('TOKEN')
CHANNEL = os.getenv('CHANNEL')
SAVE_FILE = os.getenv('SAVE_FILE', 'players.json')

_CONSTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'consts')


def _load_yml(filename):
    path = os.path.join(_CONSTS_DIR, filename)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except (FileNotFoundError, yaml.YAMLError) as e:
        logging.error(f"Ошибка загрузки {filename}: {e}")
        raise


MONSTERS = _load_yml('monsters.yml')
ITEM_DESCRIPTIONS = _load_yml('item_descriptions.yml')
ITEMS = _load_yml('items.yml')
BLACK_MARKET_ITEMS = _load_yml('black_market_items.yml')
_RACES = _load_yml('races.yml')
_CLASSES = _load_yml('classes.yml')


class RPGbot(commands.Bot):
    """Twitch RPG бот с системой уровней, боев, экономики и кражи."""

    CD_XP: int = 300
    CD_FIGHT: int = 90
    CD_PVP: int = 60
    CD_STEAL: int = 300

    def __init__(self):
        """Инициализация бота с загрузкой данных игроков и настройкой параметров."""
        super().__init__(token=TOKEN, prefix='!', initial_channels=[CHANNEL])
        self.player_service = PlayerService(_CLASSES, ITEMS)
        self.combat_service = CombatService()
        self.inventory_service = InventoryService()
        self.player_service.players = self.load_players()
        self.black_market_items = []
        self.black_market_last_refresh = 0
        self.pending_duels = {}
        self.races = _RACES
        self.classes = _CLASSES

    # ------------------------------------------------------------------
    # players — свойство для обратной совместимости с тестами
    # ------------------------------------------------------------------

    @property
    def players(self) -> dict:
        return self.player_service.players

    @players.setter
    def players(self, value: dict):
        self.player_service.players = value

    # ------------------------------------------------------------------
    # Обёртки для обратной совместимости с тестами
    # ------------------------------------------------------------------

    def load_players(self) -> dict:
        """Загрузить данные игроков из JSON-файла с проверкой структуры."""
        if not os.path.exists(SAVE_FILE):
            logging.info(f"Файл {SAVE_FILE} не существует, создаётся пустой словарь игроков.")
            return {}

        lock = FileLock(f"{SAVE_FILE}.lock")
        with lock:
            try:
                with open(SAVE_FILE, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        logging.warning(f"Файл {SAVE_FILE} пуст.")
                        return {}
                    players = json.loads(content)
                    default_player = {
                        'level': 1,
                        'xp': 0,
                        'gold': 15,
                        'inventory': [],
                        'equipment': {'weapon': None, 'armor': None, 'helmet': None, 'pet': None, 'amulet': None},
                        'last_xp_time': 0,
                        'last_fight_time': 0,
                        'last_pvp_time': 0,
                        'last_steal_time': 0,
                        'alms_unteal': 0,
                        'pvp_wins': 0,
                        'pvp_losses': 0,
                        'prison': False,
                        'prison_until': 0,
                        'race': None,
                        'class': None,
                        'current_hp': None
                    }
                    for user, data in players.items():
                        for key, value in default_player.items():
                            if key not in data:
                                data[key] = value
                        # Миграция старого ключа с опечаткой
                        if 'steal_time_unteal' in data:
                            data['last_steal_time'] = data.pop('steal_time_unteal')
                        if data['current_hp'] is None:
                            data['current_hp'] = self.get_equipment_bonuses(data)[2] + calculate_hp(data['level'])
                    return players
            except (json.JSONDecodeError, IOError) as e:
                logging.error(f"Ошибка загрузки {SAVE_FILE}: {e}")
                print(f"⚠️ Ошибка загрузки {SAVE_FILE}: {e}")
                return {}

    def save_players(self):
        """Сохранить данные игроков в JSON-файл с резервной копией."""
        lock = FileLock(f"{SAVE_FILE}.lock")
        with lock:
            try:
                if os.path.exists(SAVE_FILE):
                    shutil.copy(SAVE_FILE, f"{SAVE_FILE}.bak")
                    logging.info(f"Создана резервная копия {SAVE_FILE}.bak")
                with open(SAVE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.players, f, ensure_ascii=False, indent=2)
                logging.info(f"Данные игроков сохранены в {SAVE_FILE}")
            except IOError as e:
                logging.error(f"Ошибка сохранения {SAVE_FILE}: {e}")
                print(f"⚠️ Ошибка сохранения {SAVE_FILE}: {e}")

    def try_level_up(self, player: dict) -> bool:
        """Обёртка: делегирует player_service."""
        return self.player_service.try_level_up(player)

    def get_equipment_bonuses(self, player: dict) -> tuple:
        """Обёртка: делегирует player_service."""
        return self.player_service.get_equipment_bonuses(player)

    async def check_cooldown(self, player: dict, key: str, cooldown: int, ctx) -> bool:
        """Обёртка: проверяет кулдаун и отправляет сообщение при необходимости."""
        ok, remain = self.player_service.check_cooldown(player, key, cooldown)
        if not ok:
            await ctx.send(f'{ctx.author.name}, подожди {remain} секунд.')
        return ok

    # ------------------------------------------------------------------
    # Вспомогательные методы бота
    # ------------------------------------------------------------------

    def refresh_black_market(self):
        """Обновить ассортимент черного рынка."""
        self.black_market_items = random.sample(BLACK_MARKET_ITEMS, k=min(3, len(BLACK_MARKET_ITEMS)))
        self.black_market_last_refresh = time.time()
        logging.info("Чёрный рынок обновлён")

    async def event_ready(self):
        """Обработчик события готовности бота."""
        print(f'✅ Бот подключен как {self.nick}')
        logging.info(f'Бот подключен как {self.nick}')

    # ------------------------------------------------------------------
    # Команды
    # ------------------------------------------------------------------

    @commands.command(name='черныйрынок')
    async def cmd_black_market(self, ctx):
        """Показать доступные предметы на черном рынке."""
        now = time.time()
        if now - self.black_market_last_refresh > 600 or not self.black_market_items:
            self.refresh_black_market()

        msg_lines = ['🕶️ Тёмный торговец шепчет:\nСегодня в продаже:']
        for idx, item in enumerate(self.black_market_items, start=1):
            msg_lines.append(f'{idx}. {item["name"]} — {item["price"]} золота ({item["description"]})')
        msg_lines.append('Купи через команду !купить <номер>')

        for line in msg_lines:
            await ctx.send(line)

    @commands.command(name='купить')
    @requires_character
    async def cmd_buy(self, ctx):
        """Купить предмет с черного рынка."""
        user = ctx.author.name.lower()

        parts = ctx.message.content.strip().split()
        if len(parts) != 2 or not parts[1].isdigit():
            await ctx.send('Используй формат: !купить <номер>')
            return

        choice = int(parts[1]) - 1
        if choice < 0 or choice >= len(self.black_market_items):
            await ctx.send(f'{ctx.author.name}, нет такого товара.')
            return

        player = self.players[user]
        item = self.black_market_items[choice]

        if player['gold'] < item['price']:
            await ctx.send(f'{ctx.author.name}, у тебя недостаточно золота.')
            return

        player['gold'] -= item['price']
        player['inventory'].append(item['name'])
        self.save_players()
        logging.info(f"{user} купил {item['name']} за {item['price']} золота")

        if item['type'] in ['pet', 'amulet', 'consumable']:
            await ctx.send(f'{ctx.author.name}, ты приобрел {item["type"]}: {item["name"]}! '
                           f'Используй {"!надеть" if item["type"] in ["pet", "amulet"] else "!использовать"} {item["name"]}.')
        else:
            await ctx.send(f'{ctx.author.name}, ты купил: {item["name"]}')

    @commands.command(name='старт')
    async def cmd_start(self, ctx):
        """Создать нового персонажа."""
        user = ctx.author.name.lower()
        if user in self.players:
            await ctx.send(f'{ctx.author.name}, ты уже начал игру!')
            return

        max_hp = calculate_hp(1)
        self.players[user] = {
            'level': 1,
            'xp': 0,
            'gold': 0,
            'inventory': [],
            'equipment': {'weapon': None, 'armor': None, 'helmet': None, 'pet': None, 'amulet': None},
            'last_xp_time': 0,
            'last_fight_time': 0,
            'last_pvp_time': 0,
            'last_steal_time': 0,
            'pvp_wins': 0,
            'pvp_losses': 0,
            'prison': False,
            'prison_until': 0,
            'race': None,
            'class': None,
            'current_hp': max_hp
        }
        self.save_players()
        logging.info(f"Создан персонаж для {user}")
        await ctx.send(f'{ctx.author.name}, персонаж создан! Уровень 1, XP 0, золото 0. Выбери расу (!раса) и класс (!класс).')

    @commands.command(name='статус')
    async def cmd_status(self, ctx):
        """Показать статус игрока."""
        parts = ctx.message.content.strip().split()
        target = parts[1].lstrip('@').lower() if len(parts) == 2 else ctx.author.name.lower()

        if target not in self.players:
            await ctx.send(f'{ctx.author.name}, у {target} нет персонажа.')
            return

        p = self.players[target]
        lvl = p["level"]
        min_bonus, max_bonus, hp_bonus = self.get_equipment_bonuses(p)
        base_min = 5 + lvl * 2
        base_max = 10 + lvl * 3
        dmg_range = f'{base_min + min_bonus}-{base_max + max_bonus}'
        hp = calculate_hp(lvl) + hp_bonus
        current_hp = p.get('current_hp', hp)

        msg = f'{target} — Уровень {lvl}, XP {p["xp"]}, Золото {p["gold"]}, Урон {dmg_range}, HP {current_hp}/{hp}'
        if p.get('race'):
            msg += f', Раса: {p["race"]}'
        if p.get('class'):
            msg += f', Класс: {p["class"]}'
        await ctx.send(msg)

        now = time.time()
        status = []
        if p.get('xp_buff_until', 0) > now:
            status.append('📈 +50% XP (бордель)')
        if p.get('xp_penalty', False):
            status.append('⚠️ -50% XP (штраф)')
        if p.get('prison', False) and p.get('prison_until', 0) > now:
            remain = int(p['prison_until'] - now)
            status.append(f'🔒 В тюрьме ({remain} сек.)')
        if p.get('attack_buff_until', 0) > now:
            remain = int(p['attack_buff_until'] - now)
            status.append(f'⚔️ +10% урона ({remain} сек.)')
        if status:
            await ctx.send(f'{target}, активные эффекты: {", ".join(status)}')

    @commands.command(name='инвентарь')
    @requires_character
    async def cmd_inventory(self, ctx):
        """Показать инвентарь игрока."""
        user = ctx.author.name.lower()
        inventory = self.players[user].get('inventory', [])
        if not inventory:
            await ctx.send(f'@{ctx.author.name}, твой инвентарь пуст.')
            return

        item_counts = Counter(inventory)
        formatted_items = [f'{item} x{count}' if count > 1 else item for item, count in item_counts.items()]
        await ctx.send(f'@{ctx.author.name}, инвентарь: {", ".join(formatted_items)}')

    @commands.command(name='экипировка')
    @requires_character
    async def cmd_equipment(self, ctx):
        """Показать текущую экипировку игрока."""
        user = ctx.author.name.lower()
        equipment = self.players[user].get('equipment', {})
        eq_text = ', '.join(
            f'{slot.capitalize()}: {equipment[slot] if equipment[slot] else "—"}'
            for slot in ['weapon', 'armor', 'helmet', 'pet', 'amulet']
        )
        await ctx.send(f'🛡️ Экипировка {ctx.author.name}: {eq_text}')

    @commands.command(name='опыт')
    @requires_character
    async def cmd_xp(self, ctx):
        """Получить опыт с учетом кулдауна и баффов."""
        user = ctx.author.name.lower()
        player = self.players[user]

        if not await self.check_cooldown(player, 'last_xp_time', self.CD_XP, ctx):
            return

        base_xp = 50
        race_bonus = self.races[player.get('race', '')].get('xp_bonus', 0) if player.get('race') else 0
        class_bonus = self.classes[player.get('class', '')].get('xp_bonus', 0) if player.get('class') else 0

        now = time.time()
        if player.get('xp_buff_until', 0) > now:
            base_xp = int(base_xp * 1.5)
        if player.get('xp_penalty', False):
            base_xp = int(base_xp * 0.5)
        base_xp = int(base_xp * (1 + race_bonus + class_bonus))

        player['xp'] += base_xp
        leveled = self.try_level_up(player)
        self.save_players()
        logging.info(f"{user} получил {base_xp} XP")

        msg = f'{ctx.author.name}, получено {base_xp} XP. Текущий XP: {player["xp"]}'
        if leveled:
            msg += f' 📈 Уровень повышен! Теперь уровень {player["level"]}.'
        await ctx.send(msg)

    @commands.command(name='надеть')
    @requires_character
    async def cmd_equip(self, ctx):
        """Надеть предмет из инвентаря."""
        user = ctx.author.name.lower()
        item_name = ctx.message.content.strip()[7:].strip()
        player = self.players[user]

        ok, msg = self.inventory_service.equip_item(player, item_name, ITEMS)
        if not ok:
            await ctx.send(f'{ctx.author.name}, {msg}.')
            return

        player['current_hp'] = min(
            player['current_hp'], self.player_service.get_max_hp(player)
        )
        self.save_players()
        logging.info(f"{user} надел {item_name}")
        await ctx.send(f'{ctx.author.name}, {msg}.')

    @commands.command(name='снять')
    @requires_character
    async def cmd_unequip(self, ctx):
        """Снять предмет из указанного слота."""
        user = ctx.author.name.lower()
        parts = ctx.message.content.strip().split(maxsplit=1)

        if len(parts) < 2:
            await ctx.send(f'{ctx.author.name}, укажи слот: !снять <weapon|armor|helmet|pet|amulet>')
            return

        slot = parts[1].strip().lower()
        player = self.players[user]

        ok, msg = self.inventory_service.unequip_item(player, slot)
        if not ok:
            await ctx.send(f'{ctx.author.name}, {msg}.')
            return

        player['current_hp'] = min(
            player['current_hp'], self.player_service.get_max_hp(player)
        )
        self.save_players()
        logging.info(f"{user} снял предмет из слота {slot}")
        await ctx.send(f'{ctx.author.name}, {msg}.')

    @commands.command(name='использовать')
    @requires_character
    async def cmd_use(self, ctx):
        """Использовать расходуемый предмет."""
        user = ctx.author.name.lower()
        parts = ctx.message.content.strip().split(maxsplit=1)

        if len(parts) < 2:
            await ctx.send(f'{ctx.author.name}, укажи предмет: !использовать <название>')
            return

        item_name = parts[1].strip()
        player = self.players[user]
        max_hp = self.player_service.get_max_hp(player)

        ok, msg, _ = self.inventory_service.use_item(player, item_name, ITEMS, max_hp)
        if not ok:
            await ctx.send(f'{ctx.author.name}, {msg}.')
            return

        self.save_players()
        logging.info(f"{user} использовал {item_name}")
        await ctx.send(f'{ctx.author.name}, {msg}.')

    @commands.command(name='бой')
    @requires_character
    async def cmd_fight(self, ctx):
        """Сражение с монстром."""
        user = ctx.author.name.lower()
        player = self.players[user]
        now = time.time()

        if player.get('prison', False) and player.get('prison_until', 0) > now:
            remain = int(player['prison_until'] - now)
            await ctx.send(f'@{ctx.author.name}, ты в тюрьме! Заплати взятку (!взятка) или жди {remain} сек.')
            return

        if not await self.check_cooldown(player, 'last_fight_time', self.CD_FIGHT, ctx):
            return

        parts = ctx.message.content.strip().split()
        monster_name = (
            parts[1].capitalize()
            if len(parts) > 1 and parts[1].capitalize() in MONSTERS
            else random.choice([k for k, v in MONSTERS.items() if not v.get('rare', False) or random.random() < 0.1])
        )

        level = player['level']
        min_bonus, max_bonus, hp_bonus = self.get_equipment_bonuses(player)
        player_hp = calculate_hp(level) + hp_bonus
        attack_multiplier = 1.1 if player.get('attack_buff_until', 0) > now else 1.0

        result = self.combat_service.simulate_fight(
            player, monster_name, MONSTERS, min_bonus, max_bonus, player_hp, attack_multiplier, level
        )

        _m = MONSTERS[monster_name]
        log = [f'{ctx.author.name} сражается с {monster_name}! (Монстр: HP {int(_m["base_hp"] * (1 + (level - 1) * _m.get("scale_multiplier", 0.25)))})']

        if result.won:
            player['xp'] += result.xp_gained
            player['gold'] += result.gold_gained
            if result.loot:
                player['inventory'].append(result.loot)
            player['current_hp'] = result.player_hp_left
            leveled = self.try_level_up(player)
            self.save_players()
            logging.info(f"{user} победил {monster_name}, получил {result.xp_gained} XP, {result.gold_gained} золота, дроп: {result.loot}")

            msg = f'🏆 Победа за {result.rounds} ходов! +{result.xp_gained} XP, +{result.gold_gained} золота.'
            if result.loot:
                msg += f' Дроп: {result.loot}.'
            log.append(msg)
            if leveled:
                log.append(f'📈 Уровень повышен! Текущий уровень: {player["level"]}')
        else:
            xp_loss = int(player['xp'] * 0.1)
            player['xp'] = max(0, player['xp'] - xp_loss)
            player['current_hp'] = result.player_hp_left
            log.append(f'💀 Поражение от {monster_name}... Потеряно {xp_loss} XP')
            self.save_players()
            logging.info(f"{user} проиграл {monster_name}, потеряно {xp_loss} XP")

        for line in log:
            await ctx.send(line)

    @commands.command(name='топ')
    async def cmd_top(self, ctx):
        """Показать топ-10 игроков по уровню и XP."""
        if not self.players:
            await ctx.send('Нет данных для рейтинга.')
            return
        top = sorted(self.players.items(), key=lambda i: (i[1]['level'], i[1]['xp']), reverse=True)[:10]
        result = ', '.join([f'{i + 1}. {name} (Lvl {p["level"]}, XP {p["xp"]})' for i, (name, p) in enumerate(top)])
        await ctx.send(f'🏆 ТОП игроков: {result}')

    @commands.command(name='дуэль')
    async def cmd_duel(self, ctx):
        """Вызвать игрока на дуэль."""
        challenger = ctx.author.name.lower()
        parts = ctx.message.content.strip().split()

        if len(parts) < 2:
            await ctx.send('Формат: !дуэль @ник [ставка]')
            return

        target = parts[1].lstrip('@').lower()
        amount = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() and int(parts[2]) >= 0 else 0

        if challenger == target:
            await ctx.send('Нельзя вызвать самого себя.')
            return

        if challenger not in self.players or target not in self.players:
            await ctx.send('Оба игрока должны иметь персонажей.')
            return

        if self.players[challenger]['gold'] < amount:
            await ctx.send('Недостаточно золота для ставки.')
            return

        if target in self.pending_duels:
            await ctx.send(f'{target} уже ожидает другой дуэли.')
            return

        cl = self.players[challenger]
        tl = self.players[target]
        chp = self.player_service.get_max_hp(cl)
        thp = self.player_service.get_max_hp(tl)
        cl_bon = self.get_equipment_bonuses(cl)
        tl_bon = self.get_equipment_bonuses(tl)
        cdmg = f'{5 + cl["level"] * 2 + cl_bon[0]}-{10 + cl["level"] * 3 + cl_bon[1]}'
        tdmg = f'{5 + tl["level"] * 2 + tl_bon[0]}-{10 + tl["level"] * 3 + tl_bon[1]}'

        self.pending_duels[target] = {'challenger': challenger, 'amount': amount}
        await ctx.send(
            f'⚔️ {ctx.author.name} вызывает @{target} на дуэль{" со ставкой " + str(amount) + " золота" if amount else ""}!\n'
            f'{ctx.author.name}: HP {chp}, Урон {cdmg}; @{target}: HP {thp}, Урон {tdmg}\n'
            f'@{target}, напиши !принять чтобы принять вызов.'
        )
        logging.info(f"{challenger} вызвал {target} на дуэль с ставкой {amount}")

    @commands.command(name='принять')
    @requires_character
    async def cmd_accept(self, ctx):
        """Принять вызов на дуэль."""
        defender = ctx.author.name.lower()
        now = time.time()

        if self.players[defender].get('prison', False) and self.players[defender].get('prison_until', 0) > now:
            remain = int(self.players[defender]['prison_until'] - now)
            await ctx.send(f'@{ctx.author.name}, ты в тюрьме! Заплати взятку (!взятка) или жди {remain} сек.')
            return

        if defender not in self.pending_duels:
            await ctx.send('Тебя никто не вызывал на дуэль.')
            return

        duel = self.pending_duels.pop(defender)
        challenger = duel['challenger']
        amount = duel['amount']

        if challenger not in self.players:
            await ctx.send('Игрок-вызывающий не найден.')
            return

        a = self.players[challenger]
        d = self.players[defender]

        if not await self.check_cooldown(a, 'last_pvp_time', self.CD_PVP, ctx) or \
           not await self.check_cooldown(d, 'last_pvp_time', self.CD_PVP, ctx):
            return

        if amount > 0 and (a['gold'] < amount or d['gold'] < amount):
            await ctx.send('У кого-то не хватает золота.')
            return

        if amount > 0:
            a['gold'] -= amount
            d['gold'] -= amount

        min_a, max_a, hp_a = self.get_equipment_bonuses(a)
        min_d, max_d, hp_d = self.get_equipment_bonuses(d)
        hp1 = a.get('current_hp', calculate_hp(a['level']) + hp_a)
        hp2 = d.get('current_hp', calculate_hp(d['level']) + hp_d)
        multiplier_a = 1.1 if a.get('attack_buff_until', 0) > now else 1.0
        multiplier_d = 1.1 if d.get('attack_buff_until', 0) > now else 1.0

        result = self.combat_service.simulate_duel(
            challenger, defender, a, d,
            (min_a, max_a), (min_d, max_d),
            multiplier_a, multiplier_d, hp1, hp2
        )

        result.winner_p['current_hp'] = max(1, result.hp_winner_left)
        result.loser_p['current_hp'] = self.player_service.get_max_hp(result.loser_p) // 2

        gold_msg = f' и {amount * 2} золота' if amount > 0 else ''
        result.winner_p['xp'] += result.xp_reward
        level_msg = ''
        if self.try_level_up(result.winner_p):
            level_msg = f'📈 {result.winner} повышает уровень! Теперь уровень {result.winner_p["level"]}.'

        result.winner_p['pvp_wins'] = result.winner_p.get('pvp_wins', 0) + 1
        result.loser_p['pvp_losses'] = result.loser_p.get('pvp_losses', 0) + 1
        if amount > 0:
            result.winner_p['gold'] += amount * 2
        self.save_players()
        logging.info(f"Дуэль: {result.winner} победил {result.loser}, получил {result.xp_reward} XP{gold_msg}")

        await ctx.send(f'🏁 Побеждает {result.winner}, получает {result.xp_reward} XP{gold_msg}!')
        if level_msg:
            await ctx.send(level_msg)

    @commands.command(name='отмена')
    async def cmd_cancel_duel(self, ctx):
        """Отменить вызов на дуэль."""
        user = ctx.author.name.lower()
        if user in self.pending_duels:
            self.pending_duels.pop(user)
            await ctx.send(f'{ctx.author.name}, твой вызов на дуэль отменён.')
            logging.info(f"{user} отменил входящий вызов на дуэль")
            return

        for target, duel in list(self.pending_duels.items()):
            if duel['challenger'] == user:
                self.pending_duels.pop(target)
                await ctx.send(f'{ctx.author.name}, ты отменил вызов дуэли @{target}.')
                logging.info(f"{user} отменил вызов дуэли для {target}")
                return
        await ctx.send(f'{ctx.author.name}, у тебя нет активных вызовов на дуэль.')

    @commands.command(name='пвп')
    @requires_character
    async def cmd_pvp_stats(self, ctx):
        """Показать статистику PvP."""
        user = ctx.author.name.lower()
        p = self.players[user]
        wins = p.get('pvp_wins', 0)
        losses = p.get('pvp_losses', 0)
        total = wins + losses
        winrate = f"{(wins / total * 100):.1f}%" if total > 0 else "–"
        await ctx.send(f'{ctx.author.name}, PvP: Победы: {wins}, Поражения: {losses}, Winrate: {winrate}')

    @commands.command(name='описание')
    async def cmd_description(self, ctx):
        """Показать описание предмета."""
        parts = ctx.message.content.strip().split(maxsplit=1)
        user = ctx.author.name.lower()

        if len(parts) == 2:
            item_name = parts[1].strip().lower()
            description = ITEM_DESCRIPTIONS.get(item_name)
            if description:
                await ctx.send(f'Описание {parts[1].strip()}: {description}')
            else:
                await ctx.send(f'{ctx.author.name}, описание для "{parts[1].strip()}" не найдено.')
            return

        if user not in self.players:
            await ctx.send(f'{ctx.author.name}, у тебя нет персонажа.')
            return

        inventory = self.players[user].get('inventory', [])
        if not inventory:
            await ctx.send(f'{ctx.author.name}, у тебя пустой инвентарь.')
            return

        unique_items = list(set(inventory))
        if len(unique_items) == 1:
            item_name = unique_items[0].lower()
            description = ITEM_DESCRIPTIONS.get(item_name)
            if description:
                await ctx.send(f'Описание {unique_items[0]}: {description}')
            else:
                await ctx.send(f'{ctx.author.name}, описание для "{unique_items[0]}" не найдено.')
        else:
            await ctx.send(f'{ctx.author.name}, укажи название предмета: !описание <название>. '
                           f'Инвентарь: {", ".join(unique_items)}')

    @commands.command(name='бордель')
    @requires_character
    async def cmd_brothel(self, ctx):
        """Посетить бордель для получения баффа или штрафа."""
        user = ctx.author.name.lower()
        player = self.players[user]
        cost = 100
        now = time.time()

        if player['gold'] < cost:
            await ctx.send(f'{ctx.author.name}, у тебя недостаточно золота (нужно {cost}).')
            return

        if player.get('xp_buff_until', 0) > now:
            await ctx.send(f'{ctx.author.name}, эффект уже активен. Подожди, пока он закончится.')
            return

        player['gold'] -= cost
        if random.random() < 0.25:
            player['xp_penalty'] = True
            await ctx.send(
                f'💋 {ctx.author.name}, ты подцепил что-то... XP уменьшается на 50%! Используй !лечиться за 50 золота.')
            logging.info(f"{user} получил штраф XP в борделе")
        else:
            player['xp_buff_until'] = now + 1800
            await ctx.send(
                f'💃 {ctx.author.name}, ты вдохновлён! В течение 30 минут +50% XP.')
            logging.info(f"{user} получил бафф XP в борделе")
        self.save_players()

    @commands.command(name='лечиться')
    @requires_character
    async def cmd_heal(self, ctx):
        """Вылечиться от штрафа за посещение борделя."""
        user = ctx.author.name.lower()
        player = self.players[user]
        cost = 50

        if not player.get('xp_penalty'):
            await ctx.send(f'{ctx.author.name}, тебе не нужно лечение.')
            return

        if player['gold'] < cost:
            await ctx.send(f'{ctx.author.name}, у тебя недостаточно золота (нужно {cost}).')
            return

        player['gold'] -= cost
        player['xp_penalty'] = False
        self.save_players()
        logging.info(f"{user} вылечился от штрафа XP")
        await ctx.send(f'🧼 {ctx.author.name}, ты вылечился и готов к приключениям!')

    @commands.command(name='продать')
    @requires_character
    async def cmd_sell(self, ctx):
        """Продать предмет из инвентаря."""
        user = ctx.author.name.lower()
        parts = ctx.message.content.strip().split(maxsplit=1)

        if len(parts) != 2:
            await ctx.send(f'{ctx.author.name}, укажи предмет: !продать <название>')
            return

        item_name = parts[1].strip()
        player = self.players[user]
        actual = self.inventory_service.find_item(player, item_name)

        if actual is None:
            await ctx.send(f'{ctx.author.name}, у тебя нет предмета "{item_name}".')
            return

        if actual not in ITEMS or 'price' not in ITEMS[actual]:
            await ctx.send(f'{ctx.author.name}, этот предмет нельзя продать.')
            return

        sell_price = ITEMS[actual]['price'] // 2
        player['inventory'].remove(actual)
        player['gold'] += sell_price
        self.save_players()
        logging.info(f"{user} продал {actual} за {sell_price} золота")
        await ctx.send(f'{ctx.author.name}, ты продал "{actual}" за {sell_price} золота.')

    @commands.command(name='оценить')
    @requires_character
    async def cmd_appraise(self, ctx):
        """Оценить стоимость предмета."""
        user = ctx.author.name.lower()
        parts = ctx.message.content.strip().split(maxsplit=1)

        if len(parts) < 2:
            await ctx.send(f'{ctx.author.name}, укажи предмет: !оценить <название>')
            return

        item_name = parts[1].strip()
        player = self.players[user]
        actual = self.inventory_service.find_item(player, item_name)

        if actual is None:
            await ctx.send(f'{ctx.author.name}, у тебя нет предмета "{item_name}".')
            return

        if actual not in ITEMS:
            await ctx.send(f'{ctx.author.name}, предмет "{actual}" не подлежит продаже.')
            return

        price = ITEMS[actual].get('price', 0)
        sell_price = max(price // 2, 1)
        await ctx.send(f'{ctx.author.name}, ты можешь продать "{actual}" за {sell_price} золота.')

    @commands.command(name='кража')
    @requires_character
    async def cmd_steal(self, ctx):
        """Попытаться украсть предмет у другого игрока."""
        user = ctx.author.name.lower()
        parts = ctx.message.content.strip().split(maxsplit=2)

        if len(parts) < 3:
            await ctx.send(f'{ctx.author.name}, формат: !кража @ник <предмет>')
            return

        target = parts[1].lstrip('@').lower()
        item_name = parts[2].strip()

        if target == user:
            await ctx.send(f'{ctx.author.name}, нельзя украсть у себя.')
            return

        if target not in self.players:
            await ctx.send(f'{target} не имеет персонажа.')
            return

        player = self.players[user]
        if not await self.check_cooldown(player, 'last_steal_time', self.CD_STEAL, ctx):
            return

        target_player = self.players[target]
        if self.inventory_service.find_item(target_player, item_name) is None:
            await ctx.send(f'{ctx.author.name}, у @{target} нет предмета "{item_name}".')
            return

        steal_chance = 0.1 + (
            self.classes[player.get('class', '')].get('steal_chance_bonus', 0)
            if player.get('class') else 0
        )
        if player['equipment'].get('amulet') == 'Амулет удачи':
            steal_chance += ITEMS['Амулет удачи']['effect']['steal_chance_bonus']

        if random.random() < steal_chance:
            actual = self.inventory_service.find_item(target_player, item_name)
            player['inventory'].append(actual)
            target_player['inventory'].remove(actual)
            await ctx.send(f'{ctx.author.name}, {actual} успешно украден у @{target}!')
            logging.info(f"{user} украл {actual} у {target}")
        else:
            now = time.time()
            player['prison'] = True
            player['prison_until'] = now + 600
            await ctx.send(f'@{ctx.author.name}, кража не удалась, тебя схватила стража! Ты в тюрьме на 5 минут.')
            logging.info(f"{user} провалил кражу, отправлен в тюрьму")
        self.save_players()

    @commands.command(name='взятка')
    @requires_character
    async def cmd_prison(self, ctx):
        """Заплатить взятку для выхода из тюрьмы."""
        user = ctx.author.name.lower()
        player = self.players[user]
        now = time.time()

        if not player.get('prison', False) or player.get('prison_until', 0) <= now:
            await ctx.send(f'{ctx.author.name}, ты не в тюрьме.')
            return

        cost = 50
        if player['gold'] < cost:
            await ctx.send(f'{ctx.author.name}, у тебя недостаточно золота (нужно {cost}).')
            return

        player['gold'] -= cost
        player['prison'] = False
        player['prison_until'] = 0
        self.save_players()
        logging.info(f"{user} заплатил взятку и вышел из тюрьмы")
        await ctx.send(f'@{ctx.author.name}, ты свободен!')

    @commands.command(name='таверна')
    @requires_character
    async def cmd_tavern(self, ctx):
        """Посетить таверну для получения баффа на урон."""
        user = ctx.author.name.lower()
        player = self.players[user]
        cost = 50
        now = time.time()

        if player.get('attack_buff_until', 0) > now:
            await ctx.send(f'{ctx.author.name}, бафф уже активен. Подожди, пока он закончится.')
            return

        if player['gold'] < cost:
            await ctx.send(f'{ctx.author.name}, у тебя недостаточно золота (нужно {cost}).')
            return

        player['gold'] -= cost
        player['attack_buff_until'] = now + 1800
        self.save_players()
        logging.info(f"{user} получил бафф урона в таверне")
        await ctx.send(f'🍺 {ctx.author.name}, ты отдохнул в таверне! В течение 30 минут +10% урона.')

    @commands.command(name='раса')
    @requires_character
    async def cmd_race(self, ctx):
        """Выбрать расу для персонажа."""
        user = ctx.author.name.lower()
        parts = ctx.message.content.strip().split(maxsplit=1)
        player = self.players[user]

        if len(parts) < 2:
            races = ', '.join(self.races.keys())
            await ctx.send(f'{ctx.author.name}, укажи расу: !раса <название>. Доступные расы: {races}')
            return

        race = parts[1].strip().lower()
        if race not in self.races:
            await ctx.send(f'{ctx.author.name}, раса "{race}" не существует.')
            return

        if player.get('race'):
            await ctx.send(f'{ctx.author.name}, ты уже выбрал расу: {player["race"]}.')
            return

        player['race'] = race
        player['current_hp'] = self.player_service.get_max_hp(player)
        self.save_players()
        logging.info(f"{user} выбрал расу {race}")
        await ctx.send(f'{ctx.author.name}, ты выбрал расу: {race.capitalize()}.')

    @commands.command(name='класс')
    @requires_character
    async def cmd_class(self, ctx):
        """Выбрать класс для персонажа."""
        user = ctx.author.name.lower()
        parts = ctx.message.content.strip().split(maxsplit=1)
        player = self.players[user]

        if len(parts) < 2:
            classes = ', '.join(self.classes.keys())
            await ctx.send(f'{ctx.author.name}, укажи класс: !класс <название>. Доступные классы: {classes}')
            return

        class_name = parts[1].strip().lower()
        if class_name not in self.classes:
            await ctx.send(f'{ctx.author.name}, класс "{class_name}" не существует.')
            return

        if player.get('class'):
            await ctx.send(f'{ctx.author.name}, ты уже выбрал класс: {player["class"]}.')
            return

        player['class'] = class_name
        player['current_hp'] = self.player_service.get_max_hp(player)
        self.save_players()
        logging.info(f"{user} выбрал класс {class_name}")
        await ctx.send(f'{ctx.author.name}, ты выбрал класс: {class_name.capitalize()}.')

    @commands.command(name='отдых')
    @requires_character
    async def cmd_full_heal(self, ctx):
        """Полностью восстановить HP за 5 золота."""
        user = ctx.author.name.lower()
        player = self.players[user]
        cost = 5
        max_hp = self.player_service.get_max_hp(player)

        if player['current_hp'] >= max_hp:
            await ctx.send(f'{ctx.author.name}, твоё здоровье и так полное!')
            return

        if player['gold'] < cost:
            await ctx.send(f'{ctx.author.name}, у тебя недостаточно золота (нужно {cost}).')
            return

        player['gold'] -= cost
        player['current_hp'] = max_hp
        self.save_players()
        logging.info(f"{user} полностью восстановил HP за {cost} золота")
        await ctx.send(f'🩺 {ctx.author.name}, ты полностью восстановил HP за {cost} золота!')

    @commands.command(name='подарить')
    @requires_character
    async def cmd_gift(self, ctx):
        """Подарить любой предмет из инвентаря другому игроку"""
        user = ctx.author.name.lower()
        parts = ctx.message.content.strip().split(maxsplit=2)
        player = self.players[user]

        if len(parts) != 3:
            await ctx.send(f'@{user}, формат отправки подарка: !подарить <имя персонажа> <название предмета из инвентаря>')
            return

        target = parts[1].lstrip('@').lower()
        item = parts[2].capitalize()
        item_parts = item.split()

        if target not in self.players:
            await ctx.send(f'@{user}, {target} должен иметь персонажа!')
            return

        target_player = self.players[target]

        if item_parts[0] == 'Золото':
            if len(item_parts) < 2 or not item_parts[1].isdigit():
                await ctx.send(f'@{user}, ты хоть сам понял что хочешь?)')
                return
            ok, msg = self.inventory_service.gift_gold(player, target_player, int(item_parts[1]))
            if ok:
                self.save_players()
                await ctx.send(f'@{user} подарил @{target} {item_parts[1]} золотых монет!')
            else:
                await ctx.send(f'@{user}, {msg}!')
            return

        ok, msg = self.inventory_service.gift_item(player, target_player, item)
        if ok:
            self.save_players()
            await ctx.send(f'@{user} успешно передал @{target} предмет {item}')
        else:
            await ctx.send(f'@{user}, {msg}!')


    @commands.command(name='команды')
    async def cmd_commands(self, ctx):
        """Отправить ссылку на список команд."""
        user = ctx.author.name.lower()
        await ctx.send(f'@{user} для просмотра команд иди в описание канала!')

    @commands.command(name='милостыня')
    @requires_character
    async def cmd_alms(self, ctx):
        """Попросить милостыню (раз в 5 минут)."""
        now = time.time()
        user = ctx.author.name.lower()
        player = self.players[user]
        if player['alms_unteal'] >= now:
            remain = int(player['alms_unteal'] - now) + 1
            await ctx.send(f'@{user}, шел бы ты, пока люлей не дали! До следующей попытки {remain} секунд.')
            return
        gold_given = random.choice([0, 1, 2])
        player['alms_unteal'] = now + 300
        player['gold'] += gold_given
        self.save_players()
        await ctx.send(f'@{user}, тебе дали {gold_given} монет/у, благодари господа!')


if __name__ == '__main__':  # pragma: no cover
    MODE = os.getenv('MODE', 'twitch')
    if MODE == 'local':
        from local_bot import LocalBot
        bot = LocalBot()
    else:
        bot = RPGbot()
    bot.run()
