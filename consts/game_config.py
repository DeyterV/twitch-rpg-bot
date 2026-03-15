"""Игровые константы. Все настраиваемые числа находятся здесь."""

# --- Кулдауны (секунды) ---
CD_XP: int = 300
CD_FIGHT: int = 90
CD_PVP: int = 60
CD_STEAL: int = 300
CD_ALMS: int = 300

# --- HP персонажа ---
BASE_HP: int = 30
HP_PER_LEVEL: int = 5

# --- Урон персонажа ---
DAMAGE_MIN_BASE: int = 5
DAMAGE_MIN_COEF: int = 2
DAMAGE_MAX_BASE: int = 10
DAMAGE_MAX_COEF: int = 3

# --- Прогрессия ---
XP_PER_LEVEL: int = 100          # level * XP_PER_LEVEL — порог повышения уровня
BASE_XP_GAIN: int = 50           # базовый опыт за !опыт
XP_BUFF_MULTIPLIER: float = 1.5
XP_DEBUFF_MULTIPLIER: float = 0.5
XP_LOSS_ON_DEFEAT: float = 0.1   # доля XP, теряемая при поражении от монстра

# --- Монстры ---
MOB_SCALE_MULTIPLIER_DEFAULT: float = 0.25
RARE_MOB_CHANCE: float = 0.1

# --- Боевые коэффициенты ---
ATTACK_BUFF_MULTIPLIER: float = 1.1
HP_RESTORE_RATIO: int = 2        # делитель для восстановления/потери HP

# --- PvP ---
PVP_XP_PER_LEVEL: int = 10       # XP за победу = PVP_XP_PER_LEVEL * уровень проигравшего
DUEL_BET_WIN_MULTIPLIER: int = 2  # победитель получает amount * DUEL_BET_WIN_MULTIPLIER

# --- Чёрный рынок ---
BLACK_MARKET_MAX_ITEMS: int = 3
BLACK_MARKET_REFRESH_INTERVAL: int = 600

# --- Начальное золото ---
STARTING_GOLD: int = 15

# --- Бордель ---
BROTHEL_COST: int = 100
BROTHEL_PENALTY_CHANCE: float = 0.25
BROTHEL_BUFF_DURATION: int = 1800  # 30 минут

# --- Лечение ---
HEAL_COST: int = 50               # !лечиться (от штрафа борделя)
FULL_HEAL_COST: int = 5           # !отдых (полное восстановление HP)

# --- Кража и тюрьма ---
BASE_STEAL_CHANCE: float = 0.1
STEAL_PRISON_DURATION: int = 600
BRIBE_COST: int = 50

# --- Таверна ---
TAVERN_COST: int = 50
TAVERN_BUFF_DURATION: int = 1800  # 30 минут

# --- Торговля ---
SELL_PRICE_RATIO: int = 2         # цена продажи = price // SELL_PRICE_RATIO
MIN_SELL_PRICE: int = 1           # минимальная цена при оценке

# --- Милостыня ---
ALMS_CHOICES: list = [0, 1, 2]
