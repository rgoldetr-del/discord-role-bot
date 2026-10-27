# modules/presets_data.py
# Пресеты кейсов в тематике Terraria.
# Старый нетематический пресет заменён.
# Первый кейс бесплатный (free=True): выдаётся раз в час через магазин.

PRESET_CASES = [
    # ============================================================
    # 1. СТАРТОВЫЙ / БЕСПЛАТНЫЙ КЕЙС
    # ============================================================
    {
        "name": "🌱 Стартовый кейс",
        "case_rarity": "common",
        "case_price": 0,
        "key_price": 0,
        "free": True,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 30, "roles": ["🪓 Медный топор"]},
            {"rarity": "uncommon", "chance": 25, "price": 100, "roles": ["🧪 Малое зелье здоровья"]},
            {"rarity": "rare", "chance": 12, "price": 300, "roles": ["⚔️ Деревянный меч"]},
            {"rarity": "epic", "chance": 3, "price": 1000, "roles": ["🐶 Посох зяблка"]},
        ]
    },

    # ============================================================
    # 2. БОССЫ
    # ============================================================
    {
        "name": "👑 Король Слизней",
        "case_rarity": "common",
        "case_price": 250,
        "key_price": 100,
        "rarities": [
            {"rarity": "common", "chance": 55, "price": 50, "roles": ["🟦 Слизистая верёвка"]},
            {"rarity": "uncommon", "chance": 28, "price": 150, "roles": ["🪝 Крюк-слизень"]},
            {"rarity": "rare", "chance": 13, "price": 600, "roles": ["🥷 Костюм ниндзя"]},
            {"rarity": "epic", "chance": 4, "price": 2500, "roles": ["👑 Маска Короля Слизней"]},
        ]
    },
    {
        "name": "👁️ Глаз Ктулху",
        "case_rarity": "common",
        "case_price": 450,
        "key_price": 180,
        "rarities": [
            {"rarity": "common", "chance": 50, "price": 70, "roles": ["🔍 Линза"]},
            {"rarity": "uncommon", "chance": 30, "price": 200, "roles": ["🔭 Бинокль"]},
            {"rarity": "rare", "chance": 15, "price": 800, "roles": ["🩸 Маска Глаза Ктулху"]},
            {"rarity": "epic", "chance": 5, "price": 3000, "roles": ["👁️ Подозрительный глаз"]},
        ]
    },
    {
        "name": "🐛 Пожиратель миров",
        "case_rarity": "uncommon",
        "case_price": 700,
        "key_price": 280,
        "rarities": [
            {"rarity": "common", "chance": 45, "price": 100, "roles": ["🪱 Сегмент червя"]},
            {"rarity": "uncommon", "chance": 30, "price": 350, "roles": ["🧣 Шарф червя"]},
            {"rarity": "rare", "chance": 18, "price": 1200, "roles": ["🌑 Теневая чешуя"]},
            {"rarity": "epic", "chance": 7, "price": 4500, "roles": ["🪓 Демонитовый топор"]},
        ]
    },
    {
        "name": "💀 Скелетрон",
        "case_rarity": "rare",
        "case_price": 1200,
        "key_price": 450,
        "rarities": [
            {"rarity": "common", "chance": 40, "price": 150, "roles": ["🦴 Старая кость"]},
            {"rarity": "uncommon", "chance": 30, "price": 500, "roles": ["📖 Книга черепов"]},
            {"rarity": "rare", "chance": 20, "price": 1800, "roles": ["🖐️ Рука Скелетрона"]},
            {"rarity": "epic", "chance": 10, "price": 7000, "roles": ["💀 Маска Скелетрона"]},
        ]
    },
    {
        "name": "🧱 Стена Плоти",
        "case_rarity": "rare",
        "case_price": 2200,
        "key_price": 800,
        "rarities": [
            {"rarity": "common", "chance": 35, "price": 300, "roles": ["🍖 Плоть"]},
            {"rarity": "uncommon", "chance": 30, "price": 900, "roles": ["🎯 Эмблема воина"]},
            {"rarity": "rare", "chance": 25, "price": 3500, "roles": ["🔫 Лазерная винтовка"]},
            {"rarity": "epic", "chance": 9, "price": 12000, "roles": ["🗡️ Разбиватель"]},
            {"rarity": "legendary", "chance": 1, "price": 60000, "roles": ["🧱 Душа Хардмода"]},
        ]
    },
    {
        "name": "🌸 Плантера",
        "case_rarity": "epic",
        "case_price": 5000,
        "key_price": 1800,
        "rarities": [
            {"rarity": "uncommon", "chance": 35, "price": 1000, "roles": ["🌿 Семя Плантеры"]},
            {"rarity": "rare", "chance": 35, "price": 4000, "roles": ["🌺 Маска Плантеры"]},
            {"rarity": "epic", "chance": 22, "price": 15000, "roles": ["🪄 Цветок Плантеры"]},
            {"rarity": "legendary", "chance": 7, "price": 70000, "roles": ["🎸 Гроза джунглей"]},
            {"rarity": "secret", "chance": 1, "price": 300000, "roles": ["🌳 Сердце джунглей"]},
        ]
    },
    {
        "name": "🌙 Лунный Лорд",
        "case_rarity": "secret+",
        "case_price": 60000,
        "key_price": 20000,
        "rarities": [
            {"rarity": "rare", "chance": 30, "price": 5000, "roles": ["🌑 Лунный фрагмент"]},
            {"rarity": "epic", "chance": 35, "price": 20000, "roles": ["🎭 Маска Лунного Лорда"]},
            {"rarity": "legendary", "chance": 25, "price": 100000, "roles": ["🪐 Печать Луны"]},
            {"rarity": "secret", "chance": 8, "price": 500000, "roles": ["🐙 Щупальце Владыки"]},
            {"rarity": "secret+", "chance": 2, "price": 2000000, "roles": ["🌈 Последняя Призма"]},
        ]
    },

    # ============================================================
    # 3. ПРОФЕССИИ / БЫТ
    # ============================================================
    {
        "name": "⛏️ Шахтёр",
        "case_rarity": "common",
        "case_price": 400,
        "key_price": 150,
        "rarities": [
            {"rarity": "common", "chance": 50, "price": 60, "roles": ["⛏️ Медная кирка"]},
            {"rarity": "uncommon", "chance": 30, "price": 250, "roles": ["🕯️ Шахтёрский фонарь"]},
            {"rarity": "rare", "chance": 15, "price": 1000, "roles": ["🧨 Динамит"]},
            {"rarity": "epic", "chance": 4, "price": 5000, "roles": ["⚙️ Кобальтовый бур"]},
            {"rarity": "legendary", "chance": 1, "price": 50000, "roles": ["🚜 Лазерная дрель"]},
        ]
    },
    {
        "name": "🎣 Рыбак",
        "case_rarity": "uncommon",
        "case_price": 800,
        "key_price": 300,
        "rarities": [
            {"rarity": "common", "chance": 45, "price": 100, "roles": ["🎣 Деревянная удочка"]},
            {"rarity": "uncommon", "chance": 30, "price": 400, "roles": ["🪱 Золотой червь"]},
            {"rarity": "rare", "chance": 18, "price": 1500, "roles": ["📱 Телефон рыбака"]},
            {"rarity": "epic", "chance": 6, "price": 6000, "roles": ["🐷 Свинотрон"]},
            {"rarity": "legendary", "chance": 1, "price": 80000, "roles": ["🌊 Бездонное ведро лавы"]},
        ]
    },
    {
        "name": "🧪 Зельевар",
        "case_rarity": "rare",
        "case_price": 1500,
        "key_price": 550,
        "rarities": [
            {"rarity": "common", "chance": 40, "price": 200, "roles": ["🍶 Пустая бутылка"]},
            {"rarity": "uncommon", "chance": 30, "price": 700, "roles": ["❤️ Зелье регенерации"]},
            {"rarity": "rare", "chance": 20, "price": 2500, "roles": ["💙 Зелье маны"]},
            {"rarity": "epic", "chance": 9, "price": 9000, "roles": ["💖 Эликсир жизни"]},
            {"rarity": "legendary", "chance": 1, "price": 90000, "roles": ["🪨 Философский камень"]},
        ]
    },

    # ============================================================
    # 4. ПИТОМЦЫ И МАУНТЫ
    # ============================================================
    {
        "name": "🐾 Верные питомцы",
        "case_rarity": "rare",
        "case_price": 3000,
        "key_price": 1100,
        "rarities": [
            {"rarity": "common", "chance": 35, "price": 400, "roles": ["🐱 Котёнок"]},
            {"rarity": "uncommon", "chance": 30, "price": 1200, "roles": ["🐰 Крольчонок"]},
            {"rarity": "rare", "chance": 20, "price": 4000, "roles": ["🦖 Динозаврик"]},
            {"rarity": "epic", "chance": 12, "price": 15000, "roles": ["🧚 Фея в банке"]},
            {"rarity": "legendary", "chance": 3, "price": 80000, "roles": ["👁️ Глазик Ктулху"]},
        ]
    },
    {
        "name": "🛸 Эпические маунты",
        "case_rarity": "epic",
        "case_price": 6000,
        "key_price": 2200,
        "rarities": [
            {"rarity": "uncommon", "chance": 35, "price": 1500, "roles": ["🐇 Кроличье седло"]},
            {"rarity": "rare", "chance": 35, "price": 5000, "roles": ["🦄 Седло единорога"]},
            {"rarity": "epic", "chance": 20, "price": 20000, "roles": ["🐉 Седло Пигрона"]},
            {"rarity": "legendary", "chance": 9, "price": 100000, "roles": ["🛸 Инопланетный НЛО"]},
            {"rarity": "secret+", "chance": 1, "price": 1000000, "roles": ["🚜 Буровая установка"]},
        ]
    },

    # ============================================================
    # 5. БИОМЫ И ЛОКАЦИИ
    # ============================================================
    {
        "name": "🔥 Ад",
        "case_rarity": "epic",
        "case_price": 4000,
        "key_price": 1500,
        "rarities": [
            {"rarity": "common", "chance": 35, "price": 600, "roles": ["🔥 Адский камень"]},
            {"rarity": "uncommon", "chance": 30, "price": 1800, "roles": ["🌋 Огненный цветок"]},
            {"rarity": "rare", "chance": 22, "price": 7000, "roles": ["🌞 Солнечная ярость"]},
            {"rarity": "epic", "chance": 10, "price": 25000, "roles": ["🔱 Демоническое копьё"]},
            {"rarity": "legendary", "chance": 3, "price": 120000, "roles": ["☄️ Адский жнец"]},
        ]
    },
    {
        "name": "🏰 Данж",
        "case_rarity": "epic",
        "case_price": 4500,
        "key_price": 1700,
        "rarities": [
            {"rarity": "common", "chance": 35, "price": 700, "roles": ["🗝️ Золотой ключ"]},
            {"rarity": "uncommon", "chance": 30, "price": 2000, "roles": ["🛡️ Кобальтовый щит"]},
            {"rarity": "rare", "chance": 22, "price": 8000, "roles": ["🔫 Ручной пистолет"]},
            {"rarity": "epic", "chance": 10, "price": 30000, "roles": ["🌀 Акватон"]},
            {"rarity": "legendary", "chance": 3, "price": 140000, "roles": ["🔨 Молот Паладина"]},
        ]
    },

    # ============================================================
    # 6. СОБЫТИЯ И ЭНДГЕЙМ
    # ============================================================
    {
        "name": "👽 Марсианское безумие",
        "case_rarity": "legendary",
        "case_price": 12000,
        "key_price": 4500,
        "rarities": [
            {"rarity": "rare", "chance": 35, "price": 6000, "roles": ["📡 Марсианский провод"]},
            {"rarity": "epic", "chance": 35, "price": 25000, "roles": ["🔫 Лазерный пулемёт"]},
            {"rarity": "legendary", "chance": 25, "price": 120000, "roles": ["🛸 Антигравитационный крюк"]},
            {"rarity": "secret", "chance": 4, "price": 600000, "roles": ["👽 Ксенопосох"]},
            {"rarity": "secret+", "chance": 1, "price": 3000000, "roles": ["🌌 Инопланетный скипетр"]},
        ]
    },
    {
        "name": "⚔️ Зенит",
        "case_rarity": "secret+",
        "case_price": 80000,
        "key_price": 30000,
        "rarities": [
            {"rarity": "legendary", "chance": 45, "price": 100000, "roles": ["🗡️ Терра-клинок"]},
            {"rarity": "secret", "chance": 40, "price": 400000, "roles": ["🐱 Мяумур"]},
            {"rarity": "secret+", "chance": 15, "price": 2500000, "roles": ["⚔️ Зенит"]},
        ]
    },
]

FREE_CASE_INDEX = 0  # индекс бесплатного кейса в PRESET_CASES