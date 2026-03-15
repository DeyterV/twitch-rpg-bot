import random
from dataclasses import dataclass
from typing import Optional

from services.player_service import calculate_damage


@dataclass
class FightResult:
    won: bool
    rounds: int
    xp_gained: int
    gold_gained: int
    loot: Optional[str]
    player_hp_left: int


@dataclass
class DuelResult:
    winner: str
    loser: str
    winner_p: dict
    loser_p: dict
    hp_winner_left: int
    xp_reward: int
    rounds: int


class CombatService:
    """Симуляция боёв с монстрами и PvP дуэлей."""

    def simulate_fight(
        self,
        player: dict,
        monster_name: str,
        monsters: dict,
        min_bonus: int,
        max_bonus: int,
        player_hp: int,
        attack_multiplier: float,
        level: int,
    ) -> FightResult:
        """Симуляция боя игрока с монстром. Возвращает FightResult."""
        base = monsters[monster_name]
        scale_factor = 1 + (level - 1) * 0.25
        monster_hp = int(base['base_hp'] * scale_factor)
        monster_attack = int(base['base_attack'] * scale_factor)

        current_hp = player.get('current_hp', player_hp)
        rounds = 0

        while monster_hp > 0 and current_hp > 0:
            rounds += 1
            total_attack = int(
                (calculate_damage(level) + random.randint(min_bonus, max_bonus))
                * attack_multiplier
            )
            monster_hp -= total_attack
            if monster_hp <= 0:
                break
            current_hp -= monster_attack

        if current_hp > 0:
            xp_gained = random.randint(*base['xp_reward'])
            gold_gained = random.randint(*base['gold_reward'])
            loot = (
                random.choice(base['loot'])
                if base['loot'] and random.random() < base['loot_chance']
                else None
            )
            player_hp_left = min(current_hp + player_hp // 2, player_hp)
            return FightResult(
                won=True,
                rounds=rounds,
                xp_gained=xp_gained,
                gold_gained=gold_gained,
                loot=loot,
                player_hp_left=player_hp_left,
            )
        else:
            return FightResult(
                won=False,
                rounds=rounds,
                xp_gained=0,
                gold_gained=0,
                loot=None,
                player_hp_left=player_hp // 2,
            )

    def simulate_duel(
        self,
        challenger_name: str,
        defender_name: str,
        a: dict,
        d: dict,
        bonuses_a: tuple,
        bonuses_d: tuple,
        multiplier_a: float,
        multiplier_d: float,
        hp1: int,
        hp2: int,
    ) -> DuelResult:
        """Симуляция PvP дуэли. Возвращает DuelResult."""
        min_a, max_a = bonuses_a
        min_d, max_d = bonuses_d

        if random.random() < 0.5:
            att_name, def_name = challenger_name, defender_name
            att_p, def_p = a, d
            hp_att, hp_def = hp1, hp2
            att_bonus = (min_a, max_a)
            def_bonus = (min_d, max_d)
            att_mult, def_mult = multiplier_a, multiplier_d
        else:
            att_name, def_name = defender_name, challenger_name
            att_p, def_p = d, a
            hp_att, hp_def = hp2, hp1
            att_bonus = (min_d, max_d)
            def_bonus = (min_a, max_a)
            att_mult, def_mult = multiplier_d, multiplier_a

        rounds = 1
        while True:
            damage = self._calc_damage(att_p, att_bonus[0], att_bonus[1], att_mult)
            hp_def -= damage
            if hp_def <= 0:
                winner, loser = att_name, def_name
                winner_p, loser_p = att_p, def_p
                hp_winner_left = hp_att
                break

            damage = self._calc_damage(def_p, def_bonus[0], def_bonus[1], def_mult)
            hp_att -= damage
            if hp_att <= 0:
                winner, loser = def_name, att_name
                winner_p, loser_p = def_p, att_p
                hp_winner_left = hp_def
                break

            rounds += 1

        xp_reward = 10 * loser_p['level']
        return DuelResult(
            winner=winner,
            loser=loser,
            winner_p=winner_p,
            loser_p=loser_p,
            hp_winner_left=hp_winner_left,
            xp_reward=xp_reward,
            rounds=rounds,
        )

    @staticmethod
    def _calc_damage(player: dict, min_b: int, max_b: int, multiplier: float) -> int:
        """Рассчитать урон игрока в раунде."""
        base = calculate_damage(player['level'])
        bonus = random.randint(min_b, max_b)
        return int((base + bonus) * multiplier)
