import random
import time

from consts.game_config import (
    BASE_HP, HP_PER_LEVEL,
    DAMAGE_MIN_BASE, DAMAGE_MIN_COEF, DAMAGE_MAX_BASE, DAMAGE_MAX_COEF,
    XP_PER_LEVEL,
)


def calculate_hp(level: int) -> int:
    """Рассчитать максимальное HP персонажа по уровню."""
    return BASE_HP + (level - 1) * HP_PER_LEVEL


def calculate_damage(level: int) -> int:
    """Рассчитать базовый урон персонажа по уровню."""
    return random.randint(
        DAMAGE_MIN_BASE + level * DAMAGE_MIN_COEF,
        DAMAGE_MAX_BASE + level * DAMAGE_MAX_COEF,
    )


class PlayerService:
    """Управление данными игроков: бонусы экипировки, уровни, кулдауны."""

    def __init__(self, classes_data: dict, items_data: dict):
        self.players: dict = {}
        self.classes = classes_data
        self.items = items_data

    def get_equipment_bonuses(self, player: dict) -> tuple:
        """Рассчитать бонусы от экипировки и класса."""
        equip = player.get('equipment', {})
        attack_bonus_min, attack_bonus_max, hp_bonus = 0, 0, 0

        for slot, item_name in equip.items():
            if item_name and item_name in self.items:
                item = self.items[item_name]
                ab = item['attack_bonus']
                ab_min, ab_max = ab if isinstance(ab, (tuple, list)) else (ab, ab)
                attack_bonus_min += ab_min
                attack_bonus_max += ab_max
                hp_bonus += item.get('hp_bonus', 0)

        player_class = player.get('class')
        if player_class in self.classes:
            class_info = self.classes[player_class]
            ab = class_info['attack_bonus']
            ab_min, ab_max = ab if isinstance(ab, (tuple, list)) else (ab, ab)
            attack_bonus_min += ab_min
            attack_bonus_max += ab_max
            hp_bonus += class_info.get('hp_bonus', 0)

        return attack_bonus_min, attack_bonus_max, hp_bonus

    def get_max_hp(self, player: dict) -> int:
        """Максимальное HP с учётом уровня и экипировки."""
        return calculate_hp(player['level']) + self.get_equipment_bonuses(player)[2]

    def try_level_up(self, player: dict) -> bool:
        """Проверить и повысить уровень игрока, если достаточно XP."""
        leveled_up = False
        while player['xp'] >= player['level'] * XP_PER_LEVEL:
            player['xp'] -= player['level'] * XP_PER_LEVEL
            player['level'] += 1
            leveled_up = True
            player['current_hp'] = self.get_max_hp(player)
        return leveled_up

    def check_cooldown(self, player: dict, key: str, cooldown: int) -> tuple:
        """Проверить кулдаун. Возвращает (разрешено, оставшиеся_секунды)."""
        now = time.time()
        last_time = player.get(key, 0)
        if now - last_time < cooldown:
            return False, int(cooldown - (now - last_time)) + 1
        player[key] = now
        return True, 0
