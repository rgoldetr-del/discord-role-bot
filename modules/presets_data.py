# modules/presets_data.py
# Пресеты кейсов в тематике Terraria: 25 кейсов, от дешёвых к дорогим.
# Первый кейс [1] 🌱 Greenery — бесплатный (free=True): выдаётся раз в час через /shop.
# Шансы всегда: common > uncommon > rare > epic > legendary > secret > secret+

PRESET_CASES = [
    # ---------- Набор 1: common (стартовые) ----------
    {
        "name": "[1] 🌱 Greenery",
        "case_rarity": "common",
        "case_price": 0,
        "key_price": 0,
        "free": True,
        "rarities": [
            {"rarity": "common", "chance": 60, "price": 20, "roles": ["🌱 Спринт"]},
            {"rarity": "uncommon", "chance": 28, "price": 50, "roles": ["🌿 Травник"]},
            {"rarity": "rare", "chance": 10, "price": 120, "roles": ["🌳 Древолюб"]},
            {"rarity": "epic", "chance": 2, "price": 400, "roles": ["🍄 Грибник"]},
        ]
    },
    {
        "name": "[1] ⛏️ Copper Miner",
        "case_rarity": "common",
        "case_price": 150,
        "key_price": 60,
        "rarities": [
            {"rarity": "common", "chance": 55, "price": 40, "roles": ["⛏️ Медная кирка"]},
            {"rarity": "uncommon", "chance": 30, "price": 90, "roles": ["🟤 Медный шлем"]},
            {"rarity": "rare", "chance": 13, "price": 250, "roles": ["🪨 Медная кольчуга"]},
            {"rarity": "epic", "chance": 2, "price": 700, "roles": ["💧 Пещерный фонарь"]},
        ]
    },
    {
        "name": "[1] 🌲 Living Wood",
        "case_rarity": "common",
        "case_price": 200,
        "key_price": 80,
        "rarities": [
            {"rarity": "common", "chance": 50, "price": 50, "roles": ["🪵 Живая древесина"]},
            {"rarity": "uncommon", "chance": 32, "price": 120, "roles": ["🌰 Жёлудь"]},
            {"rarity": "rare", "chance": 15, "price": 300, "roles": ["🐿️ Белка"]},
            {"rarity": "epic", "chance": 3, "price": 900, "roles": ["🦉 Сова"]},
        ]
    },
    {
        "name": "[1] ☁️ Sky Island",
        "case_rarity": "uncommon",
        "case_price": 300,
        "key_price": 120,
        "rarities": [
            {"rarity": "common", "chance": 45, "price": 70, "roles": ["☁️ Облако"]},
            {"rarity": "uncommon", "chance": 35, "price": 160, "roles": ["🌈 Радужный кирпич"]},
            {"rarity": "rare", "chance": 17, "price": 420, "roles": ["🪽 Крылья ангела"]},
            {"rarity": "epic", "chance": 3, "price": 1200, "roles": ["⚡ Звёздная ярость"]},
        ]
    },
    {
        "name": "[1] 🎃 Pumpkin Moon",
        "case_rarity": "uncommon",
        "case_price": 400,
        "key_price": 150,
        "rarities": [
            {"rarity": "common", "chance": 42, "price": 90, "roles": ["🎃 Тыква"]},
            {"rarity": "uncommon", "chance": 36, "price": 200, "roles": ["👻 Призрак"]},
            {"rarity": "rare", "chance": 18, "price": 500, "roles": ["🟩 Слизень"]},
            {"rarity": "epic", "chance": 4, "price": 1500, "roles": ["🌕 Оборотень"]},
        ]
    },

    # ---------- Набор 2: uncommon/rare ----------
    {
        "name": "[2] ❄️ Frost Legion",
        "case_rarity": "uncommon",
        "case_price": 600,
        "key_price": 250,
        "rarities": [
            {"rarity": "common", "chance": 40, "price": 150, "roles": ["❄️ Снежок"]},
            {"rarity": "uncommon", "chance": 35, "price": 320, "roles": ["🧊 Ледяной блок"]},
            {"rarity": "rare", "chance": 20, "price": 800, "roles": ["⛄ Снеговик"]},
            {"rarity": "epic", "chance": 5, "price": 2200, "roles": ["🥶 Ледяной лук"]},
        ]
    },
    {
        "name": "[2] 🔥 Inferno Prepper",
        "case_rarity": "uncommon",
        "case_price": 750,
        "key_price": 300,
        "rarities": [
            {"rarity": "common", "chance": 40, "price": 180, "roles": ["🔥 Адский камень"]},
            {"rarity": "uncommon", "chance": 34, "price": 400, "roles": ["🌋 Обсидиан"]},
            {"rarity": "rare", "chance": 20, "price": 1000, "roles": ["☄️ Метеорит"]},
            {"rarity": "epic", "chance": 6, "price": 2800, "roles": ["🔥 Огненные перчатки"]},
        ]
    },
    {
        "name": "[2] 🧪 Alchemist",
        "case_rarity": "rare",
        "case_price": 900,
        "key_price": 350,
        "rarities": [
            {"rarity": "common", "chance": 35, "price": 200, "roles": ["🧪 Зелье лечения"]},
            {"rarity": "uncommon", "chance": 35, "price": 450, "roles": ["⚗️ Зелье маны"]},
            {"rarity": "rare", "chance": 22, "price": 1200, "roles": ["🟣 Зелье регенерации"]},
            {"rarity": "epic", "chance": 8, "price": 3200, "roles": ["✨ Зелье невидимости"]},
        ]
    },
    {
        "name": "[2] 🧟 Undead Army",
        "case_rarity": "rare",
        "case_price": 1100,
        "key_price": 420,
        "rarities": [
            {"rarity": "common", "chance": 35, "price": 250, "roles": ["🧟 Зомби"]},
            {"rarity": "uncommon", "chance": 34, "price": 550, "roles": ["💀 Скелет"]},
            {"rarity": "rare", "chance": 22, "price": 1400, "roles": ["🩸 Вампир"]},
            {"rarity": "epic", "chance": 9, "price": 4000, "roles": ["🧟 Франкенштейн"]},
        ]
    },
    {
        "name": "[2] 🌸 Hallow Guardian",
        "case_rarity": "rare",
        "case_price": 1300,
        "key_price": 500,
        "rarities": [
            {"rarity": "common", "chance": 32, "price": 300, "roles": ["🌸 Единорог"]},
            {"rarity": "uncommon", "chance": 34, "price": 650, "roles": ["🦄 Пикси"]},
            {"rarity": "rare", "chance": 24, "price": 1600, "roles": ["🔔 Светящийся меч"]},
            {"rarity": "epic", "chance": 10, "price": 4500, "roles": ["👼 Фея"]},
        ]
    },

    # ---------- Набор 3: rare/epic ----------
    {
        "name": "[3] 👑 Royal Guard",
        "case_rarity": "rare",
        "case_price": 1800,
        "key_price": 700,
        "rarities": [
            {"rarity": "common", "chance": 30, "price": 400, "roles": ["🏹 Стражник"]},
            {"rarity": "uncommon", "chance": 32, "price": 900, "roles": ["🛡️ Рыцарский щит"]},
            {"rarity": "rare", "chance": 26, "price": 2200, "roles": ["⚔️ Экскалибур"]},
            {"rarity": "epic", "chance": 12, "price": 6000, "roles": ["👑 Корона"]},
        ]
    },
    {
        "name": "[3] 🌊 Dungeon Deep",
        "case_rarity": "epic",
        "case_price": 2400,
        "key_price": 950,
        "rarities": [
            {"rarity": "uncommon", "chance": 35, "price": 800, "roles": ["🟦 Кобальтовый шлем"]},
            {"rarity": "rare", "chance": 35, "price": 2400, "roles": ["🗝️ Золотой ключ"]},
            {"rarity": "epic", "chance": 22, "price": 7000, "roles": ["💙 Синий меч"]},
            {"rarity": "legendary", "chance": 8, "price": 20000, "roles": ["🐉 Дракон подземелья"]},
        ]
    },
    {
        "name": "[3] 🕷️ Spider Nest",
        "case_rarity": "epic",
        "case_price": 3000,
        "key_price": 1200,
        "rarities": [
            {"rarity": "uncommon", "chance": 32, "price": 1000, "roles": ["🕷️ Паук"]},
            {"rarity": "rare", "chance": 34, "price": 2800, "roles": ["🕸️ Паутина"]},
            {"rarity": "epic", "chance": 24, "price": 8000, "roles": ["👑 Королева пауков"]},
            {"rarity": "legendary", "chance": 10, "price": 24000, "roles": ["🌑 Тёмный жрец"]},
        ]
    },
    {
        "name": "[3] 🌙 Night Owl",
        "case_rarity": "epic",
        "case_price": 3600,
        "key_price": 1400,
        "rarities": [
            {"rarity": "rare", "chance": 35, "price": 3200, "roles": ["🌙 Лунный амулет"]},
            {"rarity": "epic", "chance": 40, "price": 9000, "roles": ["🦉 Ночной дозор"]},
            {"rarity": "legendary", "chance": 20, "price": 26000, "roles": ["⭐ Звёздная пушка"]},
            {"rarity": "secret", "chance": 5, "price": 90000, "roles": ["🌌 Пустотный странник"]},
        ]
    },
    {
        "name": "[3] ⚡ Storm Caller",
        "case_rarity": "epic",
        "case_price": 4200,
        "key_price": 1600,
        "rarities": [
            {"rarity": "rare", "chance": 34, "price": 3600, "roles": ["⛈️ Грозовой посох"]},
            {"rarity": "epic", "chance": 40, "price": 10000, "roles": ["🌩️ Молниеносец"]},
            {"rarity": "legendary", "chance": 20, "price": 30000, "roles": ["🌪️ Торнадо"]},
            {"rarity": "secret", "chance": 6, "price": 100000, "roles": ["⚡ Громобой"]},
        ]
    },

    # ---------- Набор 4: legendary ----------
    {
        "name": "[4] 🌌 Cosmos Walker",
        "case_rarity": "legendary",
        "case_price": 6000,
        "key_price": 2400,
        "rarities": [
            {"rarity": "rare", "chance": 30, "price": 5000, "roles": ["🌠 Метеоритный меч"]},
            {"rarity": "epic", "chance": 32, "price": 14000, "roles": ["🪐 Планетарный диск"]},
            {"rarity": "legendary", "chance": 28, "price": 40000, "roles": ["☀️ Солнечный камень"]},
            {"rarity": "secret", "chance": 10, "price": 150000, "roles": ["🌌 Млечный путь"]},
        ]
    },
    {
        "name": "[4] 🐉 Dragon Cult",
        "case_rarity": "legendary",
        "case_price": 7500,
        "key_price": 3000,
        "rarities": [
            {"rarity": "epic", "chance": 35, "price": 16000, "roles": ["🐲 Дракончик"]},
            {"rarity": "legendary", "chance": 40, "price": 45000, "roles": ["🐉 Древний дракон"]},
            {"rarity": "secret", "chance": 20, "price": 180000, "roles": ["🔥 Огненный дракон"]},
            {"rarity": "secret+", "chance": 5, "price": 900000, "roles": ["🐉 Владыка драконов"]},
        ]
    },
    {
        "name": "[4] ⚙️ Mechanist",
        "case_rarity": "legendary",
        "case_price": 9000,
        "key_price": 3600,
        "rarities": [
            {"rarity": "epic", "chance": 35, "price": 18000, "roles": ["⚙️ Шестерёнка"]},
            {"rarity": "legendary", "chance": 40, "price": 50000, "roles": ["🤖 Механический бур"]},
            {"rarity": "secret", "chance": 20, "price": 200000, "roles": ["🛸 НЛО"]},
            {"rarity": "secret+", "chance": 5, "price": 1000000, "roles": ["🦾 Кибертитан"]},
        ]
    },
    {
        "name": "[4] 💀 Skeletron Prime",
        "case_rarity": "legendary",
        "case_price": 11000,
        "key_price": 4400,
        "rarities": [
            {"rarity": "epic", "chance": 30, "price": 20000, "roles": ["💀 Череп"]},
            {"rarity": "legendary", "chance": 42, "price": 60000, "roles": ["🦴 Скелетрон"]},
            {"rarity": "secret", "chance": 22, "price": 240000, "roles": ["⚙️ Скелетрон Прайм"]},
            {"rarity": "secret+", "chance": 6, "price": 1200000, "roles": ["☠️ Владыка костей"]},
        ]
    },
    {
        "name": "[4] 🌿 Plantera Bloom",
        "case_rarity": "legendary",
        "case_price": 13000,
        "key_price": 5200,
        "rarities": [
            {"rarity": "legendary", "chance": 45, "price": 70000, "roles": ["🌿 Плантера"]},
            {"rarity": "secret", "chance": 40, "price": 280000, "roles": ["🌺 Гигантский бутон"]},
            {"rarity": "secret+", "chance": 15, "price": 1500000, "roles": ["🌳 Мировое древо"]},
        ]
    },

    # ---------- Набор 5: secret (кристальные) ----------
    {
        "name": "[5] 🌀 Portal Mage",
        "case_rarity": "secret",
        "case_price": 0,
        "key_price": 0,
        "case_crystal_price": 50,
        "key_crystal_price": 20,
        "rarities": [
            {"rarity": "legendary", "chance": 40, "price": 0, "roles": [], "coins": 5000, "crystals": 5},
            {"rarity": "secret", "chance": 45, "price": 0, "roles": [], "coins": 15000, "crystals": 15},
            {"rarity": "secret+", "chance": 15, "price": 0, "roles": [], "coins": 50000, "crystals": 50},
        ]
    },
    {
        "name": "[5] 🌑 Shadow Dweller",
        "case_rarity": "secret",
        "case_price": 0,
        "key_price": 0,
        "case_crystal_price": 75,
        "key_crystal_price": 30,
        "rarities": [
            {"rarity": "legendary", "chance": 35, "price": 0, "roles": [], "coins": 8000, "crystals": 8},
            {"rarity": "secret", "chance": 48, "price": 0, "roles": [], "coins": 25000, "crystals": 25},
            {"rarity": "secret+", "chance": 17, "price": 0, "roles": [], "coins": 80000, "crystals": 80},
        ]
    },
    {
        "name": "[5] 🌠 Star Sculptor",
        "case_rarity": "secret",
        "case_price": 0,
        "key_price": 0,
        "case_crystal_price": 100,
        "key_crystal_price": 40,
        "rarities": [
            {"rarity": "legendary", "chance": 30, "price": 0, "roles": [], "coins": 12000, "crystals": 12},
            {"rarity": "secret", "chance": 50, "price": 0, "roles": [], "coins": 40000, "crystals": 40},
            {"rarity": "secret+", "chance": 20, "price": 0, "roles": [], "coins": 120000, "crystals": 120},
        ]
    },
    {
        "name": "[5] 🌌 Nebula Weaver",
        "case_rarity": "secret",
        "case_price": 0,
        "key_price": 0,
        "case_crystal_price": 150,
        "key_crystal_price": 60,
        "rarities": [
            {"rarity": "secret", "chance": 55, "price": 0, "roles": [], "coins": 60000, "crystals": 60},
            {"rarity": "secret+", "chance": 45, "price": 0, "roles": [], "coins": 200000, "crystals": 200},
        ]
    },
    {
        "name": "[5] 🌃 Moon Lord",
        "case_rarity": "secret+",
        "case_price": 0,
        "key_price": 0,
        "case_crystal_price": 250,
        "key_crystal_price": 100,
        "rarities": [
            {"rarity": "secret", "chance": 40, "price": 0, "roles": [], "coins": 100000, "crystals": 100},
            {"rarity": "secret+", "chance": 60, "price": 0, "roles": [], "coins": 500000, "crystals": 500},
        ]
    },
]

FREE_CASE_INDEX = 0
