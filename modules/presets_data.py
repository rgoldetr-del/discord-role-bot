# modules/presets_data.py
# ======================================================================
# Пресеты кейсов в тематике Terraria: 26 кейсов, от дешёвых к дорогим.
#
# Экономика (гармонизирована, EV ~70% от цены открытия):
#   - шансы единые для всех кейсов: common 60 / uncommon 28 / rare 10 / epic 2
#     (в кейсах с secret-дропом: 55 / 26 / 10 / 7 / 2);
#   - рыночная цена роли (sell_price) подобрана так, чтобы ожидаемая
#     ценность выпадения составляла ~70% стоимости (кейс + ключ);
#   - [1]-[4] — за монеты, [5] — за кристаллы (топ-контент, кристаллы
#     добываются колесом, мини-играми и secret-дропом кейсов [5]);
#   - первый кейс 🌱 Greenery бесплатный (free=True): раз в час через /shop.
#
# ВАЖНО про роли: все имена — реальные предметы/броня Terraria (официальная
# русская локализация). Код установки пресетов переиспользует существующие
# роли по имени и НИКОГДА не создаёт копии с цифрами на конце.
# ======================================================================

PRESET_CASES = [
    # ---------- Набор [1]: common (стартовые, монеты) ----------
    {
        "name": "🌱 Greenery",
        "case_rarity": "common",
        "case_price": 0,
        "key_price": 0,
        "free": True,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 10, "roles": ["Солнечный цветок"]},
            {"rarity": "uncommon", "chance": 28, "price": 25, "roles": ["Светящийся гриб"]},
            {"rarity": "rare", "chance": 10, "price": 60, "roles": ["Лунный цветок"]},
            {"rarity": "epic", "chance": 2, "price": 150, "roles": ["Цветок смерти"]},
        ]
    },
    {
        "name": "⛏️ Copper Miner",
        "case_rarity": "common",
        "case_price": 150,
        "key_price": 60,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 65, "roles": ["Медная кирка"]},
            {"rarity": "uncommon", "chance": 28, "price": 160, "roles": ["Медный шлем"]},
            {"rarity": "rare", "chance": 10, "price": 400, "roles": ["Медная кольчуга"]},
            {"rarity": "epic", "chance": 2, "price": 1000, "roles": ["Медные поножи"]},
        ]
    },
    {
        "name": "🌲 Living Wood",
        "case_rarity": "common",
        "case_price": 200,
        "key_price": 80,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 85, "roles": ["Древесина"]},
            {"rarity": "uncommon", "chance": 28, "price": 210, "roles": ["Жёлудь"]},
            {"rarity": "rare", "chance": 10, "price": 520, "roles": ["Красное дерево"]},
            {"rarity": "epic", "chance": 2, "price": 1300, "roles": ["Сова"]},
        ]
    },
    {
        "name": "🏜️ Desert",
        "case_rarity": "common",
        "case_price": 300,
        "key_price": 120,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 130, "roles": ["Кактус"]},
            {"rarity": "uncommon", "chance": 28, "price": 320, "roles": ["Мандибула муравьиного льва"]},
            {"rarity": "rare", "chance": 10, "price": 800, "roles": ["Мумия"]},
            {"rarity": "epic", "chance": 2, "price": 2000, "roles": ["Запретная броня"]},
        ]
    },

    # ---------- Набор [2]: uncommon (монеты) ----------
    {
        "name": "☁️ Sky Island",
        "case_rarity": "uncommon",
        "case_price": 500,
        "key_price": 200,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 220, "roles": ["Облако в бутылке"]},
            {"rarity": "uncommon", "chance": 28, "price": 550, "roles": ["Звёздная ярость"]},
            {"rarity": "rare", "chance": 10, "price": 1400, "roles": ["Летающий ковёр"]},
            {"rarity": "epic", "chance": 2, "price": 3500, "roles": ["Гарпун"]},
        ]
    },
    {
        "name": "💀 Dungeon",
        "case_rarity": "uncommon",
        "case_price": 700,
        "key_price": 280,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 300, "roles": ["Золотой ключ"]},
            {"rarity": "uncommon", "chance": 28, "price": 750, "roles": ["Кобальтовый щит"]},
            {"rarity": "rare", "chance": 10, "price": 1900, "roles": ["Мурасама"]},
            {"rarity": "epic", "chance": 2, "price": 4700, "roles": ["Водяной шар"]},
        ]
    },
    {
        "name": "🌴 Jungle",
        "case_rarity": "uncommon",
        "case_price": 900,
        "key_price": 360,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 390, "roles": ["Споры джунглей"]},
            {"rarity": "uncommon", "chance": 28, "price": 975, "roles": ["Джунглевая броня"]},
            {"rarity": "rare", "chance": 10, "price": 2400, "roles": ["Посох регенерации"]},
            {"rarity": "epic", "chance": 2, "price": 6000, "roles": ["Амазонка"]},
        ]
    },
    {
        "name": "❄️ Snow Biome",
        "case_rarity": "uncommon",
        "case_price": 1100,
        "key_price": 440,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 480, "roles": ["Лёд"]},
            {"rarity": "uncommon", "chance": 28, "price": 1200, "roles": ["Метель в бутылке"]},
            {"rarity": "rare", "chance": 10, "price": 3000, "roles": ["Ледяное лезвие"]},
            {"rarity": "epic", "chance": 2, "price": 7500, "roles": ["Морозная броня"]},
        ]
    },
    {
        "name": "😈 Corruption",
        "case_rarity": "uncommon",
        "case_price": 1400,
        "key_price": 560,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 610, "roles": ["Демонитовая руда"]},
            {"rarity": "uncommon", "chance": 28, "price": 1500, "roles": ["Демонический лук"]},
            {"rarity": "rare", "chance": 10, "price": 3800, "roles": ["Теневая броня"]},
            {"rarity": "epic", "chance": 2, "price": 9500, "roles": ["Ночной край"]},
        ]
    },

    # ---------- Набор [3]: rare (монеты) ----------
    {
        "name": "👑 King Slime",
        "case_rarity": "rare",
        "case_price": 2000,
        "key_price": 800,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 870, "roles": ["Гель"]},
            {"rarity": "uncommon", "chance": 28, "price": 2200, "roles": ["Слизневая корона"]},
            {"rarity": "rare", "chance": 10, "price": 5400, "roles": ["Ниндзя-броня"]},
            {"rarity": "epic", "chance": 2, "price": 13500, "roles": ["Слизневое седло"]},
        ]
    },
    {
        "name": "🐝 Queen Bee",
        "case_rarity": "rare",
        "case_price": 2500,
        "key_price": 1000,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 1100, "roles": ["Мед"]},
            {"rarity": "uncommon", "chance": 28, "price": 2700, "roles": ["Пчелиное ружьё"]},
            {"rarity": "rare", "chance": 10, "price": 6800, "roles": ["Пчелиная броня"]},
            {"rarity": "epic", "chance": 2, "price": 17000, "roles": ["Пчелиные коленки"]},
        ]
    },
    {
        "name": "🔥 Underworld",
        "case_rarity": "rare",
        "case_price": 1800,
        "key_price": 720,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 790, "roles": ["Адский камень"]},
            {"rarity": "uncommon", "chance": 28, "price": 2000, "roles": ["Огненный цветок"]},
            {"rarity": "rare", "chance": 10, "price": 5000, "roles": ["Раскалённая броня"]},
            {"rarity": "epic", "chance": 2, "price": 12500, "roles": ["Феникс"]},
        ]
    },
    {
        "name": "👅 Wall of Flesh",
        "case_rarity": "rare",
        "case_price": 2200,
        "key_price": 880,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 960, "roles": ["Блок плоти"]},
            {"rarity": "uncommon", "chance": 28, "price": 2400, "roles": ["Эмблема стрелка"]},
            {"rarity": "rare", "chance": 10, "price": 6000, "roles": ["Кровавый молот"]},
            {"rarity": "epic", "chance": 2, "price": 15000, "roles": ["Эмблема воина"]},
        ]
    },
    {
        "name": "🌌 Hardmode Metals",
        "case_rarity": "rare",
        "case_price": 2800,
        "key_price": 1100,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 1200, "roles": ["Кобальтовая руда"]},
            {"rarity": "uncommon", "chance": 28, "price": 3000, "roles": ["Мифриловая наковальня"]},
            {"rarity": "rare", "chance": 10, "price": 7500, "roles": ["Титановый слиток"]},
            {"rarity": "epic", "chance": 2, "price": 19000, "roles": ["Кирка-топор"]},
        ]
    },
    {
        "name": "🌈 Hallow",
        "case_rarity": "rare",
        "case_price": 3200,
        "key_price": 1300,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 1400, "roles": ["Пыль пикси"]},
            {"rarity": "uncommon", "chance": 28, "price": 3500, "roles": ["Освящённая броня"]},
            {"rarity": "rare", "chance": 10, "price": 8800, "roles": ["Кристаллический осколок"]},
            {"rarity": "epic", "chance": 2, "price": 22000, "roles": ["Экскалибур"]},
        ]
    },

    # ---------- Набор [4]: epic (монеты, дорого) ----------
    {
        "name": "🌺 Plantera",
        "case_rarity": "epic",
        "case_price": 5000,
        "key_price": 2000,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 2200, "roles": ["Бульба плантеры"]},
            {"rarity": "uncommon", "chance": 28, "price": 5500, "roles": ["Ключ храма"]},
            {"rarity": "rare", "chance": 10, "price": 14000, "roles": ["Цветомёт"]},
            {"rarity": "epic", "chance": 2, "price": 35000, "roles": ["Сеялка"]},
        ]
    },
    {
        "name": "🗿 Golem",
        "case_rarity": "epic",
        "case_price": 6500,
        "key_price": 2600,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 2800, "roles": ["Ящерные кирпичи"]},
            {"rarity": "uncommon", "chance": 28, "price": 7000, "roles": ["Кулак голема"]},
            {"rarity": "rare", "chance": 10, "price": 17500, "roles": ["Жалящая пушка"]},
            {"rarity": "epic", "chance": 2, "price": 44000, "roles": ["Киркопила"]},
        ]
    },
    {
        "name": "🎃 Pumpkin Moon",
        "case_rarity": "epic",
        "case_price": 8000,
        "key_price": 3200,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 3500, "roles": ["Тыква"]},
            {"rarity": "uncommon", "chance": 28, "price": 8700, "roles": ["Вороний посох"]},
            {"rarity": "rare", "chance": 10, "price": 22000, "roles": ["Жезл летучей мыши"]},
            {"rarity": "epic", "chance": 2, "price": 55000, "roles": ["Клинок всадника"]},
        ]
    },
    {
        "name": "❄️ Frost Moon",
        "case_rarity": "epic",
        "case_price": 10000,
        "key_price": 4000,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 4400, "roles": ["Снежный ком"]},
            {"rarity": "uncommon", "chance": 28, "price": 11000, "roles": ["Эльфийский плавильщик"]},
            {"rarity": "rare", "chance": 10, "price": 27000, "roles": ["Снежная пушка"]},
            {"rarity": "epic", "chance": 2, "price": 68000, "roles": ["Северный полюс"]},
        ]
    },
    {
        "name": "👽 Martian Madness",
        "case_rarity": "epic",
        "case_price": 12000,
        "key_price": 4800,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 5200, "roles": ["Марсианская обшивка"]},
            {"rarity": "uncommon", "chance": 28, "price": 13000, "roles": ["Лазерный пулемёт"]},
            {"rarity": "rare", "chance": 10, "price": 33000, "roles": ["Ключ космической машины"]},
            {"rarity": "epic", "chance": 2, "price": 82000, "roles": ["Электросферный гранатомёт"]},
        ]
    },

    # ---------- Набор [5]: secret (кристаллы, эндгейм) ----------
    {
        "name": "🌿 Chlorophyte",
        "case_rarity": "epic",
        "case_price": 0,
        "key_price": 0,
        "case_crystal_price": 6,
        "key_crystal_price": 2,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 500, "roles": ["Хлорофитовая руда"]},
            {"rarity": "uncommon", "chance": 28, "price": 1250, "roles": ["Хлорофитовая броня"]},
            {"rarity": "rare", "chance": 10, "price": 3100, "roles": ["Хлорофитовая кирка"]},
            {"rarity": "epic", "chance": 2, "price": 7800, "roles": ["Дракс"]},
        ]
    },
    {
        "name": "🏰 Jungle Temple",
        "case_rarity": "epic",
        "case_price": 0,
        "key_price": 0,
        "case_crystal_price": 10,
        "key_crystal_price": 4,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 870, "roles": ["Солнечный камень"]},
            {"rarity": "uncommon", "chance": 28, "price": 2200, "roles": ["Око голема"]},
            {"rarity": "rare", "chance": 10, "price": 5400, "roles": ["Тепловой луч"]},
            {"rarity": "epic", "chance": 2, "price": 13500, "roles": ["Посох земли"]},
        ]
    },
    {
        "name": "🐟 Duke Fishron",
        "case_rarity": "legendary",
        "case_price": 0,
        "key_price": 0,
        "case_crystal_price": 15,
        "key_crystal_price": 6,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 1300, "roles": ["Пузырёмёт"]},
            {"rarity": "uncommon", "chance": 28, "price": 3300, "roles": ["Цунами"]},
            {"rarity": "rare", "chance": 10, "price": 8200, "roles": ["Крылья рыброна"]},
            {"rarity": "epic", "chance": 2, "price": 20000, "roles": ["Флэирон"]},
        ]
    },
    {
        "name": "🌙 Lunar Events",
        "case_rarity": "secret",
        "case_price": 0,
        "key_price": 0,
        "case_crystal_price": 25,
        "key_crystal_price": 10,
        "rarities": [
            {"rarity": "common", "chance": 55, "price": 1600, "roles": ["Солнечный фрагмент"]},
            {"rarity": "uncommon", "chance": 26, "price": 4000, "roles": ["Фрагмент туманности"]},
            {"rarity": "rare", "chance": 10, "price": 10000, "roles": ["Вихревой фрагмент"]},
            {"rarity": "epic", "chance": 7, "price": 26000, "roles": ["Фрагмент звёздной пыли"]},
            # secret-дроп: 2 кристалла вместо роли
            {"rarity": "secret", "chance": 2, "price": 0,
             "coins": 0, "crystals": 2},
        ]
    },
    {
        "name": "🌕 Moon Lord",
        "case_rarity": "secret",
        "case_price": 0,
        "key_price": 0,
        "case_crystal_price": 35,
        "key_crystal_price": 14,
        "rarities": [
            {"rarity": "common", "chance": 55, "price": 2300, "roles": ["Люминитовая руда"]},
            {"rarity": "uncommon", "chance": 26, "price": 5700, "roles": ["Мяумер"]},
            {"rarity": "rare", "chance": 10, "price": 14500, "roles": ["Гнев звёзд"]},
            {"rarity": "epic", "chance": 7, "price": 36000, "roles": ["Зенит"]},
            # secret-дроп: 3 кристалла вместо роли
            {"rarity": "secret", "chance": 2, "price": 0,
             "coins": 0, "crystals": 3},
        ]
    },
    {
        "name": "🔮 Prism",
        "case_rarity": "secret+",
        "case_price": 0,
        "key_price": 0,
        "case_crystal_price": 45,
        "key_crystal_price": 18,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 3900, "roles": ["Последняя призма"]},
            {"rarity": "uncommon", "chance": 28, "price": 9800, "roles": ["Туманное пламя"]},
            {"rarity": "rare", "chance": 10, "price": 24000, "roles": ["Солнечное извержение"]},
            {"rarity": "epic", "chance": 2, "price": 60000, "roles": ["Рассвет"]},
        ]
    },
]
