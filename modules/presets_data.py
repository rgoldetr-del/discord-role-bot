# modules/presets_data.py
# Пресеты кейсов в тематике Terraria: 5 наборов по 5 кейсов, от дешёвых к дорогим.
# Первый кейс набора [1] — бесплатный (free=True): выдаётся раз в час через /shop.

PRESET_CASES = [
    # ---------- Набор 1: common ----------
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
            {"rarity": "common", "chance": 55, "price": 40, "roles": ["⛏️ Медноруб"]},
            {"rarity": "uncommon", "chance": 30, "price": 90, "roles": ["🟤 Копатель"]},
            {"rarity": "rare", "chance": 13, "price": 250, "roles": ["🪨 Камнедробилка"]},
            {"rarity": "epic", "chance": 2, "price": 700, "roles": ["💧 Пещерный странник"]},
        ]
    },
    {
        "name": "[1] 🌲 Living Wood",
        "case_rarity": "common",
        "case_price": 200,
        "key_price": 80,
        "rarities": [
            {"rarity": "common", "chance": 50, "price": 50, "roles": ["🪵 Живое дерево"]},
            {"rarity": "uncommon", "chance": 32, "price": 120, "roles": ["🌰 Орех"]},
            {"rarity": "rare", "chance": 15, "price": 300, "roles": ["🐿️ Белка-стрелок"]},
            {"rarity": "epic", "chance": 3, "price": 900, "roles": ["🦉 Лунная сова"]},
        ]
    },
    {
        "name": "[1] ☁️ Sky Island",
        "case_rarity": "uncommon",
        "case_price": 300,
        "key_price": 120,
        "rarities": [
            {"rarity": "common", "chance": 45, "price": 70, "roles": ["☁️ Облачник"]},
            {"rarity": "uncommon", "chance": 35, "price": 160, "roles": ["🌈 Радужник"]},
            {"rarity": "rare", "chance": 17, "price": 420, "roles": ["🪽 Гарпия"]},
            {"rarity": "epic", "chance": 3, "price": 1200, "roles": ["⚡ Молниеносец"]},
        ]
    },
    {
        "name": "[1] 🎃 Pumpkin Moon",
        "case_rarity": "uncommon",
        "case_price": 400,
        "key_price": 150,
        "rarities": [
            {"rarity": "common", "chance": 42, "price": 90, "roles": ["🎃 Тыквоголов"]},
            {"rarity": "uncommon", "chance": 36, "price": 200, "roles": ["👻 Призрак"]},
            {"rarity": "rare", "chance": 18, "price": 500, "roles": ["🟩 Слим"]},
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
            {"rarity": "uncommon", "chance": 35, "price": 320, "roles": ["🧊 Ледяной голем"]},
            {"rarity": "rare", "chance": 20, "price": 800, "roles": ["⛄ Морозник"]},
            {"rarity": "epic", "chance": 5, "price": 2200, "roles": ["🥶 Повелитель льда"]},
        ]
    },
    {
        "name": "[2] 🔥 Inferno Prepper",
        "case_rarity": "uncommon",
        "case_price": 750,
        "key_price": 300,
        "rarities": [
            {"rarity": "common", "chance": 40, "price": 180, "roles": ["🔥 Уголёк"]},
            {"rarity": "uncommon", "chance": 34, "price": 400, "roles": ["🌋 Магмоголов"]},
            {"rarity": "rare", "chance": 20, "price": 1000, "roles": ["☄️ Кометоносец"]},
            {"rarity": "epic", "chance": 6, "price": 2800, "roles": ["🔥 Адский жнец"]},
        ]
    },
    {
        "name": "[2] 🧪 Alchemist",
        "case_rarity": "rare",
        "case_price": 900,
        "key_price": 350,
        "rarities": [
            {"rarity": "common", "chance": 35, "price": 200, "roles": ["🧪 Зельевар"]},
            {"rarity": "uncommon", "chance": 35, "price": 450, "roles": ["⚗️ Микстура"]},
            {"rarity": "rare", "chance": 22, "price": 1200, "roles": ["🟣 Философ"]},
            {"rarity": "epic", "chance": 8, "price": 3200, "roles": ["✨ Эликсирщик"]},
        ]
    },
    {
        "name": "[2] 🧟 Undead Army",
        "case_rarity": "rare",
        "case_price": 1100,
        "key_price": 420,
        "rarities": [
            {"rarity": "common", "chance": 35, "price": 250, "roles": ["🧟 Зомби-фермер"]},
            {"rarity": "uncommon", "chance": 34, "price": 550, "roles": ["💀 Скелет-лучник"]},
            {"rarity": "rare", "chance": 22, "price": 1400, "roles": ["🩸 Кровавый"]},
            {"rarity": "epic", "chance": 9, "price": 4000, "roles": ["🧟 Франкенштейн"]},
        ]
    },
    {
        "name": "[2] 🌸 Hallow Guardian",
        "case_rarity": "rare",
        "case_price": 1300,
        "key_price": 500,
        "rarities": [
            {"rarity": "common", "chance": 32, "price": 300, "roles": ["🌸 Единорожка"]},
            {"rarity": "uncommon", "chance": 34, "price": 650, "roles": ["🦄 Пегас"]},
            {"rarity": "rare", "chance": 24, "price": 1600, "roles": ["🔔 Наводящий"]},
            {"rarity": "epic", "chance": 10, "price": 4500, "roles": ["👼 Светозар"]},
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
            {"rarity": "uncommon", "chance": 32, "price": 900, "roles": ["🛡️ Оруженосец"]},
            {"rarity": "rare", "chance": 26, "price": 2200, "roles": ["⚔️ Рыцарь"]},
            {"rarity": "epic", "chance": 12, "price": 6000, "roles": ["👑 Король"]},
        ]
    },
    {
        "name": "[3] 🌊 Dungeon Deep",
        "case_rarity": "epic",
        "case_price": 2400,
        "key_price": 950,
        "rarities": [
            {"rarity": "uncommon", "chance": 35, "price": 800, "roles": ["🟦 Данженит"]},
            {"rarity": "rare", "chance": 35, "price": 2400, "roles": ["🗝️ Тюрьмовщик"]},
            {"rarity": "epic", "chance": 22, "price": 7000, "roles": ["💙 Синий шлем"]},
            {"rarity": "legendary", "chance": 8, "price": 20000, "roles": ["🐉 Дракон Подземелья"]},
        ]
    },
    {
        "name": "[3] 🕷️ Spider Nest",
        "case_rarity": "epic",
        "case_price": 3000,
        "key_price": 1200,
        "rarities": [
            {"rarity": "uncommon", "chance": 32, "price": 1000, "roles": ["🕷️ Паучонок"]},
            {"rarity": "rare", "chance": 34, "price": 2800, "roles": ["🕸️ Ткач"]},
            {"rarity": "epic", "chance": 24, "price": 8000, "roles": ["👑 Паучья королева"]},
            {"rarity": "legendary", "chance": 10, "price": 24000, "roles": ["🌑 Тёмный жрец"]},
        ]
    },
    {
        "name": "[3] 🌙 Night Owl",
        "case_rarity": "epic",
        "case_price": 3600,
        "key_price": 1400,
        "rarities": [
            {"rarity": "rare", "chance": 35, "price": 3200, "roles": ["🌙 Лунатик"]},
            {"rarity": "epic", "chance": 40, "price": 9000, "roles": ["🦉 Ночной дозор"]},
            {"rarity": "legendary", "chance": 20, "price": 26000, "roles": ["⭐ Звездочёт"]},
            {"rarity": "secret", "chance": 5, "price": 90000, "roles": ["🌌 Пустотный странник"]},
        ]
    },
    {
        "name": "[3] ⚡ Storm Caller",
        "case_rarity": "epic",
        "case_price": 4200,
        "key_price": 1600,
        "rarities": [
            {"rarity": "rare", "chance": 34, "price": 3600, "roles": ["⛈️ Грозовик"]},
            {"rarity": "epic", "chance": 40, "price": 10000, "roles": ["🌩️ Штормовестник"]},
            {"rarity": "legendary", "chance": 20, "price": 30000, "roles": ["🌪️ Циклон"]},
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
            {"rarity": "rare", "chance": 30, "price": 5000, "roles": ["🌠 Метеорит"]},
            {"rarity": "epic", "chance": 32, "price": 14000, "roles": ["🪐 Планетарий"]},
            {"rarity": "legendary", "chance": 28, "price": 40000, "roles": ["☀️ Солярий"]},
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
            {"rarity": "secret", "chance": 20, "price": 180000, "roles": ["🔥 Полыхающий"]},
            {"rarity": "secret+", "chance": 5, "price": 900000, "roles": ["🐉 Владыка драконов"]},
        ]
    },
    {
        "name": "[4] ⚙️ Mechanist",
        "case_rarity": "legendary",
        "case_price": 9000,
        "key_price": 3600,
        "rarities": [
            {"rarity": "epic", "chance": 35, "price": 18000, "roles": ["⚙️ Шестерёнщик"]},
            {"rarity": "legendary", "chance": 40, "price": 50000, "roles": ["🤖 Механист"]},
            {"rarity": "secret", "chance": 20, "price": 200000, "roles": ["🛸 НЛО-водитель"]},
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
            {"rarity": "secret", "chance": 40, "price": 280000, "roles": ["🌺 Початок"]},
            {"rarity": "secret+", "chance": 15, "price": 1500000, "roles": ["🌳 Мировое древо"]},
        ]
    },
    # ---------- Набор 5: secret ----------
    {
        "name": "[5] 🌀 Portal Mage",
        "case_rarity": "secret",
        "case_price": 20000,
        "key_price": 8000,
        "rarities": [
            {"rarity": "legendary", "chance": 40, "price": 90000, "roles": ["🌀 Портальщик"]},
            {"rarity": "secret", "chance": 45, "price": 350000, "roles": ["🧙 Маг измерения"]},
            {"rarity": "secret+", "chance": 15, "price": 2000000, "roles": ["🌌 Хранитель врат"]},
        ]
    },
    {
        "name": "[5] 🌑 Shadow Dweller",
        "case_rarity": "secret",
        "case_price": 26000,
        "key_price": 10000,
        "rarities": [
            {"rarity": "legendary", "chance": 35, "price": 100000, "roles": ["🌑 Тенеход"]},
            {"rarity": "secret", "chance": 48, "price": 400000, "roles": ["👤 Искривитель"]},
            {"rarity": "secret+", "chance": 17, "price": 2400000, "roles": ["🕳️ Пожиратель теней"]},
        ]
    },
    {
        "name": "[5] 🌠 Star Sculptor",
        "case_rarity": "secret",
        "case_price": 32000,
        "key_price": 12500,
        "rarities": [
            {"rarity": "legendary", "chance": 30, "price": 120000, "roles": ["🌠 Звездодел"]},
            {"rarity": "secret", "chance": 50, "price": 450000, "roles": ["✨ Созвездие"]},
            {"rarity": "secret+", "chance": 20, "price": 2800000, "roles": ["🌟 Скульптор звёзд"]},
        ]
    },
    {
        "name": "[5] 🌌 Nebula Weaver",
        "case_rarity": "secret",
        "case_price": 40000,
        "key_price": 16000,
        "rarities": [
            {"rarity": "secret", "chance": 55, "price": 500000, "roles": ["🌌 Туманник"]},
            {"rarity": "secret+", "chance": 45, "price": 3200000, "roles": ["🧬 Ткань туманности"]},
        ]
    },
    {
        "name": "[5] 🌃 Moon Lord",
        "case_rarity": "secret+",
        "case_price": 60000,
        "key_price": 25000,
        "rarities": [
            {"rarity": "secret", "chance": 40, "price": 600000, "roles": ["🌃 Лунный клинок"]},
            {"rarity": "secret+", "chance": 60, "price": 5000000, "roles": ["🌜 Лунный Владыка"]},
        ]
    },
]

FREE_CASE_INDEX = 0  # индекс бесплатного кейса в PRESET_CASES
