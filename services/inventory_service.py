from typing import Optional


class InventoryService:
    """Логика инвентаря и экипировки без зависимости от Twitch."""

    def find_item(self, player: dict, item_name: str) -> Optional[str]:
        """Найти предмет в инвентаре (case-insensitive). Возвращает точное имя или None."""
        for item in player.get('inventory', []):
            if item.lower() == item_name.lower():
                return item
        return None

    def equip_item(self, player: dict, item_name: str, items_data: dict) -> tuple:
        """Надеть предмет. Возвращает (успех, сообщение)."""
        actual = self.find_item(player, item_name)
        if actual is None:
            return False, f'у тебя нет предмета "{item_name}"'

        if actual not in items_data:
            return False, f'предмет "{actual}" не может быть надет'

        item_info = items_data[actual]
        slot = item_info['slot']
        if slot == 'consumable':
            return False, f'этот предмет нельзя надеть. Используй !использовать {actual}'

        current_equipped = player['equipment'].get(slot)
        if current_equipped == actual:
            return False, f'у тебя уже надет "{actual}"'

        if current_equipped:
            player['inventory'].append(current_equipped)
        player['inventory'].remove(actual)
        player['equipment'][slot] = actual

        if current_equipped:
            msg = f'ты заменил {current_equipped} на {actual} в слоте {slot}'
        else:
            msg = f'ты надел {actual} в слот {slot}'
        return True, msg

    def unequip_item(self, player: dict, slot: str) -> tuple:
        """Снять предмет из слота. Возвращает (успех, сообщение)."""
        if slot not in player['equipment'] or not player['equipment'][slot]:
            return False, f'в слоте "{slot}" ничего не надето'

        item_name = player['equipment'][slot]
        player['equipment'][slot] = None
        player['inventory'].append(item_name)
        return True, f'ты снял "{item_name}" из слота "{slot}"'

    def use_item(
        self, player: dict, item_name: str, items_data: dict, max_hp: int
    ) -> tuple:
        """Использовать расходник. Возвращает (успех, сообщение, восстановлено_hp)."""
        actual = self.find_item(player, item_name)
        if actual is None:
            return False, f'у тебя нет предмета "{item_name}"', 0

        if actual not in items_data or items_data[actual]['slot'] != 'consumable':
            return False, f'предмет "{actual}" нельзя использовать', 0

        effect = items_data[actual].get('effect', {})
        if 'heal' in effect:
            old_hp = player['current_hp']
            player['current_hp'] = min(player['current_hp'] + effect['heal'], max_hp)
            player['inventory'].remove(actual)
            healed = player['current_hp'] - old_hp
            return (
                True,
                f'ты использовал "{actual}" и восстановил {healed} HP. '
                f'Текущие HP: {player["current_hp"]}/{max_hp}',
                healed,
            )

        return False, f'предмет "{actual}" не имеет эффекта', 0

    def gift_gold(self, giver: dict, receiver: dict, amount: int) -> tuple:
        """Передать золото. Возвращает (успех, сообщение)."""
        if amount <= 0:
            return False, 'сумма должна быть больше нуля'
        if giver['gold'] < amount:
            return False, 'у тебя нет столько золота'
        giver['gold'] -= amount
        receiver['gold'] += amount
        return True, f'передано {amount} золотых монет'

    def gift_item(self, giver: dict, receiver: dict, item_name: str) -> tuple:
        """Передать предмет. Возвращает (успех, сообщение)."""
        actual = self.find_item(giver, item_name)
        if actual is None:
            return False, 'у тебя нет такого предмета в инвентаре'
        giver['inventory'].remove(actual)
        receiver['inventory'].append(actual)
        return True, f'успешно передан предмет {actual}'
