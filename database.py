# database.py
# Полная рабочая база данных.
# Если твой main.py импортирует database_addons и database_addons_extra,
# используй пустые файлы-заглушки ниже, либо убери эти импорты из main.py.

import time
import random
import aiosqlite

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

DB_PATH = "bot_database.db"

# ===== Эффекты (баффы, покупаемые в /shop и хранящиеся в инвентаре) =====

# Эффекты действуют 1 час после покупки (inventory.effect_expires_at)
# и покупаются за монеты.
# Роли-улучшения («Удача», «Богач») — бессрочные (role_type='upgradeable').
EFFECT_DURATION = 3600  # 1 час

EFFECTS = {
    "shield": {
        "name": "🛡️ Щит", "emoji": "🛡️",
        "description": "Защищает от дебаффа «Кривая рука» при открытии кейсов. Действует 1 час.",
        "price": 1500, "currency": "coins",
    },
    "discount": {
        "name": "🏷️ Скидка", "emoji": "🏷️",
        "description": "Скидка 10% на покупку кейсов и ключей в магазине. Действует 1 час.",
        "price": 1200, "currency": "coins",
    },
    "luck_charm": {
        "name": "🍀 Талисман удачи", "emoji": "🍀",
        "description": "Перекручивает пустые сектора колеса в пользу. Действует 1 час.",
        "price": 2000, "currency": "coins",
    },
    "critic": {
        "name": "⚡ Критик", "emoji": "⚡",
        "description": "10% шанс увеличить выигрыш в мини-играх на 25%. Действует 1 час.",
        "price": 1400, "currency": "coins",
    },
    "crystal_guard": {
        "name": "💎 Хранитель кристаллов", "emoji": "💎",
        "description": "15% шанс вернуть кристаллы при проигрыше в мини-играх. Действует 1 час.",
        "price": 1800, "currency": "coins",
    },
    "high_roller": {
        "name": "🔥 Азарт", "emoji": "🔥",
        "description": "Увеличивает максимальные ставки в мини-играх в 1.5 раза. Действует 1 час.",
        "price": 2200, "currency": "coins",
    },
}

EFFECT_ROLE_IDS = {
    "shield": 2001,
    "discount": 2002,
    "luck_charm": 2003,
    "critic": 2004,
    "crystal_guard": 2005,
    "high_roller": 2006,
}

FREE_CASE_NAME = "🌱 Стартовый кейс"   # бесплатный кейс: 1 покупка в час (users.last_free_case)


class Database:
    def __init__(self):
        self.db: Optional[aiosqlite.Connection] = None

    # ===== Служебные методы =====

    async def _fetchone(self, query: str, params: tuple = ()):
        async with self.db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def _fetchall(self, query: str, params: tuple = ()):
        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

                # ===== Атомарное списание монет =====
    async def create_case_return_id(
        self,
        guild_id: int,
        name: str,
        case_rarity: str,
        case_price: int,
        key_price: int,
        case_crystal_price: int = 0,
        key_crystal_price: int = 0,
        is_free: int = 0
    ) -> int:
        """Создать кейс и вернуть его ID. is_free=1 — бесплатный кейс (раз в час)."""
        async with self.db.execute(
            """
            INSERT INTO cases
                (guild_id, name, case_rarity, case_price, key_price,
                 case_crystal_price, key_crystal_price, is_active, is_free)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (guild_id, name, case_rarity, case_price, key_price,
             case_crystal_price, key_crystal_price, 1 if is_free else 0)
        ) as cursor:
            await self.db.commit()
            return cursor.lastrowid

    async def add_rarity_return_id(
        self,
        case_id: int,
        rarity: str,
        drop_chance: int,
        sell_price: int
    ) -> int:
        """Добавить редкость в кейс и вернуть её ID."""
        async with self.db.execute(
            """
            INSERT INTO case_rarities (case_id, rarity, drop_chance, sell_price)
            VALUES (?, ?, ?, ?)
            """,
            (case_id, rarity, drop_chance, sell_price)
        ) as cursor:
            await self.db.commit()
            return cursor.lastrowid

    # ===== Количество кейсов/ключей у игрока =====
    async def connect(self):
        self.db = await aiosqlite.connect(DB_PATH)
        self.db.row_factory = aiosqlite.Row
        await self.create_tables()
        await self.migrate_schema()

    async def ensure_inventory_modern(self):
        await self.migrate_schema()

    async def close(self):
        if self.db:
            await self.db.close()
            self.db = None

    async def create_tables(self):
        await self.db.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                coins INTEGER DEFAULT 0,
                crystals INTEGER DEFAULT 0,
                last_wheel_time INTEGER DEFAULT 0,
                wheel_pity INTEGER DEFAULT 0,
                broken_key_cost INTEGER DEFAULT 0,
                last_daily INTEGER DEFAULT 0,
                created_at INTEGER DEFAULT (strftime('%s', 'now')),
                PRIMARY KEY (user_id, guild_id)
            );

            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                role_type TEXT NOT NULL,
                rarity TEXT NOT NULL,
                level INTEGER DEFAULT 1,
                is_applied INTEGER DEFAULT 0,
                market_price INTEGER DEFAULT 0,
                effect_expires_at INTEGER DEFAULT 0,
                obtained_at INTEGER DEFAULT (strftime('%s', 'now'))
            );

            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                case_rarity TEXT NOT NULL,
                case_price INTEGER NOT NULL,
                key_price INTEGER NOT NULL,
                case_crystal_price INTEGER DEFAULT 0,
                key_crystal_price INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 0,
                is_free INTEGER DEFAULT 0,
                created_at INTEGER DEFAULT (strftime('%s', 'now'))
            );

            CREATE TABLE IF NOT EXISTS case_rarities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                rarity TEXT NOT NULL,
                drop_chance INTEGER NOT NULL,
                sell_price INTEGER NOT NULL,
                FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS case_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_rarity_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                FOREIGN KEY (case_rarity_id) REFERENCES case_rarities(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS player_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                case_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1,
                UNIQUE(user_id, guild_id, case_id)
            );

            CREATE TABLE IF NOT EXISTS player_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                case_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1,
                UNIQUE(user_id, guild_id, case_id)
            );

            CREATE TABLE IF NOT EXISTS market_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                inventory_id INTEGER NOT NULL,
                price INTEGER NOT NULL,
                currency TEXT DEFAULT 'coins',
                listed_at INTEGER DEFAULT (strftime('%s', 'now')),
                is_sold INTEGER DEFAULT 0,
                FOREIGN KEY (inventory_id) REFERENCES inventory(id)
            );

            CREATE TABLE IF NOT EXISTS auctions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                inventory_id INTEGER NOT NULL,
                start_price INTEGER NOT NULL,
                current_bid INTEGER DEFAULT 0,
                highest_bidder INTEGER,
                end_time INTEGER NOT NULL,
                created_at INTEGER DEFAULT (strftime('%s', 'now')),
                FOREIGN KEY (inventory_id) REFERENCES inventory(id)
            );

            CREATE TABLE IF NOT EXISTS active_games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_type TEXT NOT NULL,
                player1_id INTEGER NOT NULL,
                player2_id INTEGER,
                guild_id INTEGER NOT NULL,
                bet_amount INTEGER NOT NULL,
                game_state TEXT NOT NULL,
                created_at INTEGER DEFAULT (strftime('%s', 'now'))
            );

            CREATE INDEX IF NOT EXISTS idx_inventory_user ON inventory(user_id, guild_id);
            CREATE INDEX IF NOT EXISTS idx_market_guild ON market_listings(guild_id, is_sold);
            CREATE INDEX IF NOT EXISTS idx_auctions_guild ON auctions(guild_id, end_time);
            CREATE INDEX IF NOT EXISTS idx_keys_user ON player_keys(user_id, guild_id);
            CREATE INDEX IF NOT EXISTS idx_cases_user ON player_cases(user_id, guild_id);
            CREATE INDEX IF NOT EXISTS idx_cases_active ON cases(guild_id, is_active);
        """)
        await self.db.commit()

    async def migrate_schema(self):
        await self.db.execute("PRAGMA foreign_keys = OFF")

        await self.db.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
        await self.db.commit()

        # ===== Миграция инвентаря: убрать UNIQUE и добавить market_price =====

        inventory_info = await self._fetchall("PRAGMA table_info(inventory)")

        has_market_price = any(column["name"] == "market_price" for column in inventory_info)

        has_old_unique = False
        indexes = await self._fetchall("PRAGMA index_list(inventory)")

        for index in indexes:
            if index["unique"]:
                quoted_name = index["name"].replace('"', '""')
                columns = await self._fetchall(f'PRAGMA index_info("{quoted_name}")')
                column_names = {column["name"] for column in columns}

                if {"user_id", "guild_id", "role_id", "level"}.issubset(column_names):
                    has_old_unique = True
                    break

        version_row = await self._fetchone("SELECT version FROM schema_version LIMIT 1")

        if version_row is None:
            initial_version = 2 if has_market_price and not has_old_unique else 1
            await self.db.execute("INSERT INTO schema_version(version) VALUES (?)", (initial_version,))
            await self.db.commit()
            version = initial_version
        else:
            version = version_row["version"]

        if version < 2 or not has_market_price or has_old_unique:
            await self.db.execute("DROP TABLE IF EXISTS inventory_new")

            await self.db.execute("""
                CREATE TABLE inventory_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    role_type TEXT NOT NULL,
                    rarity TEXT NOT NULL,
                    level INTEGER DEFAULT 1,
                    is_applied INTEGER DEFAULT 0,
                    market_price INTEGER DEFAULT 0,
                    obtained_at INTEGER DEFAULT (strftime('%s', 'now'))
                )
            """)

            if has_market_price:
                await self.db.execute("""
                    INSERT INTO inventory_new (
                        id, user_id, guild_id, role_id, role_type, rarity,
                        level, is_applied, obtained_at, market_price
                    )
                    SELECT
                        id, user_id, guild_id, role_id, role_type, rarity,
                        level, is_applied, obtained_at,
                        COALESCE(market_price, CASE rarity
                            WHEN 'common' THEN 200
                            WHEN 'uncommon' THEN 800
                            WHEN 'rare' THEN 2000
                            WHEN 'epic' THEN 5000
                            WHEN 'legendary' THEN 15000
                            WHEN 'secret' THEN 50000
                            WHEN 'secret+' THEN 200000
                            ELSE 0
                        END)
                    FROM inventory
                """)
            else:
                await self.db.execute("""
                    INSERT INTO inventory_new (
                        id, user_id, guild_id, role_id, role_type, rarity,
                        level, is_applied, obtained_at, market_price
                    )
                    SELECT
                        id, user_id, guild_id, role_id, role_type, rarity,
                        level, is_applied, obtained_at,
                        CASE rarity
                            WHEN 'common' THEN 200
                            WHEN 'uncommon' THEN 800
                            WHEN 'rare' THEN 2000
                            WHEN 'epic' THEN 5000
                            WHEN 'legendary' THEN 15000
                            WHEN 'secret' THEN 50000
                            WHEN 'secret+' THEN 200000
                            ELSE 0
                        END
                    FROM inventory
                """)

            await self.db.execute("DROP TABLE inventory")
            await self.db.execute("ALTER TABLE inventory_new RENAME TO inventory")
            await self.db.execute("UPDATE schema_version SET version = 2")
            await self.db.commit()

        # ===== Миграция users на составной ключ =====

        users_info = await self._fetchall("PRAGMA table_info(users)")

        pk_cols = [
            column["name"]
            for column in sorted(users_info, key=lambda x: x["pk"])
            if column["pk"] > 0
        ]

        if pk_cols == ["user_id"]:
            await self.db.execute("DROP TABLE IF EXISTS users_new")

            await self.db.execute("""
                CREATE TABLE users_new (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    coins INTEGER DEFAULT 0,
                    crystals INTEGER DEFAULT 0,
                    last_wheel_time INTEGER DEFAULT 0,
                    wheel_pity INTEGER DEFAULT 0,
                    broken_key_cost INTEGER DEFAULT 0,
                    created_at INTEGER DEFAULT (strftime('%s', 'now')),
                    PRIMARY KEY (user_id, guild_id)
                )
            """)

            await self.db.execute("""
                INSERT OR IGNORE INTO users_new (
                    user_id, guild_id, coins, crystals,
                    last_wheel_time, wheel_pity, broken_key_cost, created_at
                )
                SELECT user_id, guild_id, coins, crystals,
                       last_wheel_time, wheel_pity, broken_key_cost, created_at
                FROM users
            """)

            await self.db.execute("DROP TABLE users")
            await self.db.execute("ALTER TABLE users_new RENAME TO users")
            await self.db.commit()

        # ===== Миграция v3: недостающие колонки (идемпотентно) =====
        # Ранее эти ALTER-ы делал modules/update_v2.py при старте бота.
        # Теперь схема полностью ведётся здесь, update_v2 не нужен.

        async def _add_column(table: str, column: str, definition: str):
            info = await self._fetchall(f"PRAGMA table_info({table})")
            if not any(col["name"] == column for col in info):
                await self.db.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                )
                await self.db.commit()

        await _add_column("users", "last_daily", "INTEGER DEFAULT 0")
        await _add_column("users", "last_free_case", "INTEGER DEFAULT 0")
        await _add_column("cases", "is_free", "INTEGER DEFAULT 0")
        await _add_column("inventory", "effect_expires_at", "INTEGER DEFAULT 0")
        await _add_column("cases", "case_crystal_price", "INTEGER DEFAULT 0")
        await _add_column("cases", "key_crystal_price", "INTEGER DEFAULT 0")
        await _add_column("market_listings", "currency", "TEXT DEFAULT 'coins'")

        # История открытий кейсов (для статистики в инвентаре/профиле)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS case_open_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                case_id INTEGER NOT NULL,
                role_id INTEGER,
                rarity TEXT,
                opened_at INTEGER DEFAULT (strftime('%s', 'now'))
            )
        """)
        await self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_history_user "
            "ON case_open_history(user_id, guild_id, opened_at)"
        )
        await self.db.commit()

        await self.db.execute("PRAGMA foreign_keys = ON")
        await self.db.commit()

    async def get_or_create_user(self, user_id: int, guild_id: int) -> Dict[str, Any]:
        row = await self._fetchone(
            "SELECT * FROM users WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        )

        if row:
            return row

        try:
            async with self.db.execute(
                "INSERT INTO users (user_id, guild_id) VALUES (?, ?)",
                (user_id, guild_id)
            ) as cursor:
                await self.db.commit()
        except aiosqlite.IntegrityError:
            pass

        row = await self._fetchone(
            "SELECT * FROM users WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        )

        return row

    async def update_coins(self, user_id: int, guild_id: int, amount: int) -> int:
        await self.get_or_create_user(user_id, guild_id)

        await self.db.execute(
            "UPDATE users SET coins = MAX(0, coins + ?) WHERE user_id = ? AND guild_id = ?",
            (amount, user_id, guild_id)
        )
        await self.db.commit()

        user = await self.get_or_create_user(user_id, guild_id)
        return user["coins"]

    async def try_spend_coins(self, user_id: int, guild_id: int, amount: int) -> bool:
        if amount <= 0:
            return True

        await self.get_or_create_user(user_id, guild_id)

        async with self.db.execute(
            """
            UPDATE users
            SET coins = coins - ?
            WHERE user_id = ? AND guild_id = ? AND coins >= ?
            """,
            (amount, user_id, guild_id, amount)
        ) as cursor:
            await self.db.commit()
            return cursor.rowcount > 0

    # ===== Атомарное списание/выдача валюты (единый источник, без патчей) =====

    async def try_spend_crystals(self, user_id: int, guild_id: int, amount: int) -> bool:
        if amount <= 0:
            return True

        await self.get_or_create_user(user_id, guild_id)

        async with self.db.execute(
            """
            UPDATE users
            SET crystals = crystals - ?
            WHERE user_id = ? AND guild_id = ? AND crystals >= ?
            """,
            (amount, user_id, guild_id, amount)
        ) as cursor:
            await self.db.commit()
            return cursor.rowcount > 0

    async def try_spend(self, user_id: int, guild_id: int, amount: int, currency: str) -> bool:
        """Списание в любой валюте: 'coins' | 'crystals'."""
        if currency == "crystals":
            return await self.try_spend_crystals(user_id, guild_id, amount)
        return await self.try_spend_coins(user_id, guild_id, amount)

    async def award_currency(self, user_id: int, guild_id: int, amount: int, currency: str):
        """Выдача в любой валюте: 'coins' | 'crystals'."""
        amount = int(amount)
        if amount <= 0:
            return
        await self.get_or_create_user(user_id, guild_id)
        column = "crystals" if currency == "crystals" else "coins"
        await self.db.execute(
            f"UPDATE users SET {column} = {column} + ? WHERE user_id = ? AND guild_id = ?",
            (amount, user_id, guild_id)
        )
        await self.db.commit()

    async def try_spend_mixed(self, user_id: int, guild_id: int, coins: int, crystals: int) -> bool:
        """Атомарное списание обеих валют одним запросом (смешанные ставки в мини-играх)."""
        coins = max(0, int(coins))
        crystals = max(0, int(crystals))

        if coins == 0 and crystals == 0:
            return True

        await self.get_or_create_user(user_id, guild_id)

        async with self.db.execute(
            """
            UPDATE users
            SET coins = coins - ?, crystals = crystals - ?
            WHERE user_id = ? AND guild_id = ? AND coins >= ? AND crystals >= ?
            """,
            (coins, crystals, user_id, guild_id, coins, crystals)
        ) as cursor:
            await self.db.commit()
            return cursor.rowcount > 0

    async def award_mixed(self, user_id: int, guild_id: int, coins: int, crystals: int):
        """Одновременная выдача обеих валют."""
        coins = max(0, int(coins))
        crystals = max(0, int(crystals))

        if coins == 0 and crystals == 0:
            return

        await self.get_or_create_user(user_id, guild_id)

        await self.db.execute(
            """
            UPDATE users
            SET coins = coins + ?, crystals = crystals + ?
            WHERE user_id = ? AND guild_id = ?
            """,
            (coins, crystals, user_id, guild_id)
        )
        await self.db.commit()

    # ===== Эффекты (роль-баффы в инвентаре, role_type='effect') =====

    async def roll_effect(self, effect: str, chance: float) -> bool:
        """Шанс срабатывания эффекта (используется в мини-играх)."""
        import random as _r
        return _r.random() < chance

    async def maybe_refund_crystals_on_loss(
        self, user_id: int, guild_id: int, lost_crystals: int
    ) -> int:
        """Эффект «Хранитель кристаллов»: 15% шанс вернуть ставку кристаллами при проигрыше."""
        if lost_crystals <= 0:
            return 0
        if not await self.has_effect(user_id, guild_id, "crystal_guard"):
            return 0
        import random as _r
        if _r.random() < 0.15:
            await self.update_crystals(user_id, guild_id, lost_crystals)
            return lost_crystals
        return 0

    async def has_effect(self, user_id: int, guild_id: int, effect: str) -> bool:
        """Эффект активен, если куплен и не истёк (действует EFFECT_DURATION = 1 час)."""
        now = int(time.time())
        row = await self._fetchone(
            """
            SELECT COUNT(*) AS count
            FROM inventory
            WHERE user_id = ? AND guild_id = ? AND role_type = 'effect'
              AND rarity = ? AND is_applied = 1
              AND COALESCE(effect_expires_at, 0) > ?
            """,
            (user_id, guild_id, effect, now)
        )
        return bool(row and row["count"] > 0)

    async def add_effect_to_inventory(self, user_id: int, guild_id: int, effect: str) -> int:
        """Продлевает эффект на 1 час (покупка суммируется). Возвращает id предмета."""
        if effect not in EFFECTS:
            return -1

        role_id = EFFECT_ROLE_IDS.get(effect, 2999)
        now = int(time.time())

        # уже есть активный эффект — просто продлеваем от текущего момента
        cur = await self.db.execute(
            """
            UPDATE inventory SET effect_expires_at = ?, is_applied = 1
            WHERE user_id = ? AND guild_id = ? AND role_type = 'effect'
              AND rarity = ? AND COALESCE(effect_expires_at, 0) > ?
            """,
            (now + EFFECT_DURATION, user_id, guild_id, effect, now),
        )
        await self.db.commit()
        if cur.rowcount > 0:
            return 0  # продление (не новый предмет)

        # есть истёкший тот же эффект — реактивируем его записью с новым сроком
        cur = await self.db.execute(
            """
            UPDATE inventory SET effect_expires_at = ?, is_applied = 1
            WHERE user_id = ? AND guild_id = ? AND role_type = 'effect' AND rarity = ?
            """,
            (now + EFFECT_DURATION, user_id, guild_id, effect),
        )
        await self.db.commit()
        if cur.rowcount > 0:
            return 0

        async with self.db.execute(
            """
            INSERT INTO inventory
            (user_id, guild_id, role_id, role_type, rarity, level, is_applied, effect_expires_at)
            VALUES (?, ?, ?, 'effect', ?, 1, 1, ?)
            """,
            (user_id, guild_id, role_id, effect, now + EFFECT_DURATION)
        ) as cursor:
            await self.db.commit()
            return cursor.lastrowid

    async def get_active_effects(self, user_id: int, guild_id: int) -> List[str]:
        """Списки активных (не истёкших) эффектов."""
        now = int(time.time())
        rows = await self._fetchall(
            """
            SELECT rarity
            FROM inventory
            WHERE user_id = ? AND guild_id = ? AND role_type = 'effect'
              AND is_applied = 1 AND COALESCE(effect_expires_at, 0) > ?
            ORDER BY id
            """,
            (user_id, guild_id, now)
        )
        return [row["rarity"] for row in rows]

    # совместимость со старым именем
    async def get_user_effects(self, user_id: int, guild_id: int) -> List[str]:
        return await self.get_active_effects(user_id, guild_id)

    # ===== Ежедневная награда =====

    async def claim_daily(self, user_id: int, guild_id: int, amount: int) -> Dict[str, Any]:
        """Атомарная выдача /daily: вернёт success=False, если уже получено сегодня."""
        await self.get_or_create_user(user_id, guild_id)
        now = int(time.time())

        async with self.db.execute(
            """
            UPDATE users
            SET last_daily = ?, coins = coins + ?
            WHERE user_id = ? AND guild_id = ? AND COALESCE(last_daily, 0) <= ?
            """,
            (now, amount, user_id, guild_id, now - 86400)
        ) as cursor:
            await self.db.commit()
            if cursor.rowcount == 0:
                user = await self.get_or_create_user(user_id, guild_id)
                cooldown_left = 86400 - (now - (user.get("last_daily") or 0))
                return {"success": False, "cooldown_left": max(0, int(cooldown_left))}
            return {"success": True, "amount": amount}

    async def reset_wheel_cooldown(self, user_id: int, guild_id: int):
        """Админ: сбросить кулдаун колеса игроку."""
        await self.db.execute(
            "UPDATE users SET last_wheel_time = 0 WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        await self.db.commit()

    async def claim_free_case(self, user_id: int, guild_id: int) -> Dict[str, Any]:
        """Бесплатный кейс «🌱 Стартовый»: 1 раз в час. Атомарно."""
        await self.get_or_create_user(user_id, guild_id)
        now = int(time.time())

        rows = await self._fetchall(
            "SELECT id, name FROM cases WHERE guild_id = ? AND is_active = 1 AND is_free = 1",
            (guild_id,)
        )
        if not rows:  # совместимость со старыми БД: поиск по имени
            rows = await self._fetchall(
                "SELECT id, name FROM cases WHERE guild_id = ? AND is_active = 1 AND name LIKE ?",
                (guild_id, "%Стартовый%")
            )
        if not rows:
            return {"success": False, "error": "Бесплатный кейс не найден. Админ: /admin → 🛠 Кейсы → ⚡ Готовые пресеты."}
        case = rows[0]

        async with self.db.execute(
            """
            UPDATE users
            SET last_free_case = ?
            WHERE user_id = ? AND guild_id = ? AND COALESCE(last_free_case, 0) <= ?
            """
            ,
            (now, user_id, guild_id, now - 3600)
        ) as cursor:
            await self.db.commit()
            if cursor.rowcount == 0:
                user = await self.get_or_create_user(user_id, guild_id)
                left = 3600 - (now - (user.get("last_free_case") or 0))
                return {"success": False, "cooldown_left": max(0, int(left))}

        ok = await self.add_case(user_id, guild_id, case["id"], 1)
        if not ok:
            await self.reset_free_case(user_id, guild_id)
            return {"success": False, "error": "Достигнут лимит хранения (50 шт.)."}
        return {"success": True, "case_id": case["id"], "case_name": case["name"]}

    async def free_case_cooldown_left(self, user_id: int, guild_id: int) -> int:
        await self.get_or_create_user(user_id, guild_id)
        user = await self.get_or_create_user(user_id, guild_id)
        left = 3600 - (int(time.time()) - (user.get("last_free_case") or 0))
        return max(0, int(left))

    async def reset_free_case(self, user_id: int, guild_id: int):
        await self.db.execute(
            "UPDATE users SET last_free_case = 0 WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        await self.db.commit()

    async def reset_daily(self, user_id: int, guild_id: int):
        """Админ: сбросить кулдаун ежедневной награды."""
        await self.db.execute(
            "UPDATE users SET last_daily = 0 WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        await self.db.commit()

    async def update_crystals(self, user_id: int, guild_id: int, amount: int) -> int:
        await self.get_or_create_user(user_id, guild_id)

        await self.db.execute(
            "UPDATE users SET crystals = MAX(0, crystals + ?) WHERE user_id = ? AND guild_id = ?",
            (amount, user_id, guild_id)
        )
        await self.db.commit()

        user = await self.get_or_create_user(user_id, guild_id)
        return user["crystals"]

    async def update_broken_key_cost(self, user_id: int, guild_id: int, cost: int):
        await self.get_or_create_user(user_id, guild_id)

        await self.db.execute(
            "UPDATE users SET broken_key_cost = ? WHERE user_id = ? AND guild_id = ?",
            (cost, user_id, guild_id)
        )
        await self.db.commit()

    async def get_player_effects(self, user_id: int, guild_id: int) -> Dict[str, Any]:
        user = await self.get_or_create_user(user_id, guild_id)

        luck_level = await self.get_upgradeable_role_level(user_id, guild_id, "luck")
        rich_level = await self.get_upgradeable_role_level(user_id, guild_id, "rich")
        clumsy = await self.has_debuff(user_id, guild_id, "clumsy_hands")

        return {
            "coins": user["coins"],
            "crystals": user["crystals"],
            "luck": luck_level,
            "rich": rich_level,
            "clumsy_hands": clumsy
        }

    # ===== Инвентарь =====

    async def add_role_to_inventory(
        self,
        user_id: int,
        guild_id: int,
        role_id: int,
        role_type: str,
        rarity: str,
        level: int = 1,
        market_price: int = 0
    ) -> int:
        """
        Добавляет роль в инвентарь.
        Дубликаты поддерживаются: если старая схема ещё содержит UNIQUE,
        создаётся копия с увеличенным уровнем.
        """
        try:
            async with self.db.execute(
                """
                INSERT INTO inventory
                (user_id, guild_id, role_id, role_type, rarity, level, market_price)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, guild_id, role_id, role_type, rarity, level, market_price)
            ) as cursor:
                await self.db.commit()
                return cursor.lastrowid
        except aiosqlite.IntegrityError:
            for attempt in range(1, 11):
                new_level = level + attempt

                try:
                    async with self.db.execute(
                        """
                        INSERT INTO inventory
                        (user_id, guild_id, role_id, role_type, rarity, level, market_price)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (user_id, guild_id, role_id, role_type, rarity, new_level, market_price)
                    ) as cursor:
                        await self.db.commit()
                        return cursor.lastrowid
                except aiosqlite.IntegrityError:
                    continue

            return -1
        except aiosqlite.OperationalError:
            async with self.db.execute(
                """
                INSERT INTO inventory
                (user_id, guild_id, role_id, role_type, rarity, level)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, guild_id, role_id, role_type, rarity, level)
            ) as cursor:
                await self.db.commit()
                return cursor.lastrowid

    async def get_user_inventory(self, user_id: int, guild_id: int):
        return await self._fetchall(
            """
            SELECT *
            FROM inventory
            WHERE user_id = ? AND guild_id = ?
            ORDER BY obtained_at DESC, id DESC
            """,
            (user_id, guild_id)
        )

    async def get_inventory_item(self, inventory_id: int, user_id: int, guild_id: int):
        return await self._fetchone(
            "SELECT * FROM inventory WHERE id = ? AND user_id = ? AND guild_id = ?",
            (inventory_id, user_id, guild_id)
        )

    async def apply_role(self, user_id: int, guild_id: int, inventory_id: int) -> bool:
        await self.db.execute(
            "UPDATE inventory SET is_applied = 1 WHERE id = ? AND user_id = ? AND guild_id = ?",
            (inventory_id, user_id, guild_id)
        )
        await self.db.commit()
        return True

    async def unapply_role(self, user_id: int, guild_id: int, inventory_id: int) -> bool:
        await self.db.execute(
            "UPDATE inventory SET is_applied = 0 WHERE id = ? AND user_id = ? AND guild_id = ?",
            (inventory_id, user_id, guild_id)
        )
        await self.db.commit()
        return True

    async def is_item_locked(self, inventory_id: int) -> bool:
        """True, если предмет участвует в активной продаже или аукционе."""
        now = int(time.time())

        row = await self._fetchone(
            """
            SELECT
                (SELECT COUNT(*) FROM market_listings
                 WHERE inventory_id = ? AND is_sold = 0) AS listings,
                (SELECT COUNT(*) FROM auctions
                 WHERE inventory_id = ? AND end_time > ?) AS auctions
            """,
            (inventory_id, inventory_id, now)
        )

        if not row:
            return False

        return bool(row["listings"] or row["auctions"])

    async def is_inventory_locked(self, inventory_id: int) -> bool:
        market_row = await self._fetchone(
            "SELECT COUNT(*) AS count FROM market_listings WHERE inventory_id = ? AND is_sold = 0",
            (inventory_id,)
        )

        if market_row and market_row["count"] > 0:
            return True

        now = int(datetime.now().timestamp())

        auction_row = await self._fetchone(
            "SELECT COUNT(*) AS count FROM auctions WHERE inventory_id = ? AND end_time > ?",
            (inventory_id, now)
        )

        return bool(auction_row and auction_row["count"] > 0)

    async def create_case(
        self,
        guild_id: int,
        name: str,
        case_rarity: str,
        case_price: int,
        key_price: int
    ) -> int:
        async with self.db.execute(
            """
            INSERT INTO cases (guild_id, name, case_rarity, case_price, key_price, is_active)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (guild_id, name, case_rarity, case_price, key_price)
        ) as cursor:
            await self.db.commit()
            return cursor.lastrowid

    async def add_rarity_to_case(
        self,
        case_id: int,
        rarity: str,
        drop_chance: int,
        sell_price: int
    ) -> int:
        async with self.db.execute(
            """
            INSERT INTO case_rarities (case_id, rarity, drop_chance, sell_price)
            VALUES (?, ?, ?, ?)
            """,
            (case_id, rarity, drop_chance, sell_price)
        ) as cursor:
            await self.db.commit()
            return cursor.lastrowid

    async def add_roles_to_case_rarity(self, case_rarity_id: int, role_ids: List[int]):
        for role_id in role_ids:
            await self.db.execute(
                "INSERT INTO case_roles (case_rarity_id, role_id) VALUES (?, ?)",
                (case_rarity_id, role_id)
            )
        await self.db.commit()

    async def remove_role_from_case_rarity(self, case_rarity_id: int, role_id: int):
        await self.db.execute(
            "DELETE FROM case_roles WHERE case_rarity_id = ? AND role_id = ?",
            (case_rarity_id, role_id)
        )
        await self.db.commit()

    async def remove_rarity_from_case(self, case_rarity_id: int):
        await self.db.execute(
            "DELETE FROM case_roles WHERE case_rarity_id = ?",
            (case_rarity_id,)
        )

        await self.db.execute(
            "DELETE FROM case_rarities WHERE id = ?",
            (case_rarity_id,)
        )

        await self.db.commit()

    async def activate_case(self, case_id: int) -> Dict[str, Any]:
        case_details = await self.get_case_details(case_id)

        if not case_details:
            return {
                "success": False,
                "error": "Кейс не найден",
                "details": []
            }

        errors = []
        warnings = []

        total_chance = sum(r["drop_chance"] for r in case_details["rarities"])

        if total_chance != 100:
            errors.append(f"Сумма шансов: {total_chance}% (должно быть 100%)")
        else:
            warnings.append(f"✅ Сумма шансов: {total_chance}%")

        empty_rarities = [
            rarity["rarity"]
            for rarity in case_details["rarities"]
            if not rarity["roles"]
        ]

        if empty_rarities:
            errors.append(f"В редкостях нет ролей: {', '.join(empty_rarities)}")
        else:
            warnings.append("✅ Во всех редкостях есть роли")

        if len(case_details["rarities"]) == 0:
            errors.append("В кейсе нет ни одной редкости")
        else:
            warnings.append(f"✅ Количество редкостей: {len(case_details['rarities'])}")

        if errors:
            return {
                "success": False,
                "error": "Кейс не может быть активирован",
                "details": errors + warnings
            }

        await self.db.execute(
            "UPDATE cases SET is_active = 1 WHERE id = ?",
            (case_id,)
        )
        await self.db.commit()

        return {
            "success": True,
            "error": None,
            "details": warnings
        }

    async def deactivate_case(self, case_id: int):
        await self.db.execute(
            "UPDATE cases SET is_active = 0 WHERE id = ?",
            (case_id,)
        )
        await self.db.commit()

    async def get_all_cases(self, guild_id: int, active_only: bool = False):
        query = "SELECT * FROM cases WHERE guild_id = ?"

        if active_only:
            query += " AND is_active = 1"

        query += " ORDER BY id"

        return await self._fetchall(query, (guild_id,))

    async def get_case_details(self, case_id: int) -> Optional[Dict[str, Any]]:
        case = await self._fetchone(
            "SELECT * FROM cases WHERE id = ?",
            (case_id,)
        )

        if not case:
            return None

        case_dict = dict(case)

        rarities = await self._fetchall(
            "SELECT * FROM case_rarities WHERE case_id = ?",
            (case_id,)
        )

        case_dict["rarities"] = []

        for rarity in rarities:
            rarity_dict = dict(rarity)

            roles = await self._fetchall(
                "SELECT role_id FROM case_roles WHERE case_rarity_id = ?",
                (rarity["id"],)
            )

            rarity_dict["roles"] = [row["role_id"] for row in roles]
            case_dict["rarities"].append(rarity_dict)

        return case_dict

    async def update_case_settings(
        self,
        case_id: int,
        name: str = None,
        case_price: int = None,
        key_price: int = None,
        case_crystal_price: int = None,
        key_crystal_price: int = None,
        is_free: int = None
    ) -> bool:
        case = await self._fetchone("SELECT * FROM cases WHERE id = ?", (case_id,))

        if not case:
            return False

        new_name = case["name"] if name is None else name.strip()
        new_case_price = case["case_price"] if case_price is None else case_price
        new_key_price = case["key_price"] if key_price is None else key_price
        new_case_crystals = case.get("case_crystal_price", 0) if case_crystal_price is None else case_crystal_price
        new_key_crystals = case.get("key_crystal_price", 0) if key_crystal_price is None else key_crystal_price

        if not new_name:
            return False

        prices = (new_case_price, new_key_price, new_case_crystals, new_key_crystals)
        if any(p < 0 for p in prices):
            return False

        await self.db.execute(
            """
            UPDATE cases
            SET name = ?, case_price = ?, key_price = ?,
                case_crystal_price = ?, key_crystal_price = ?,
                is_free = COALESCE(?, is_free)
            WHERE id = ?
            """,
            (new_name, new_case_price, new_key_price,
             new_case_crystals, new_key_crystals, is_free, case_id)
        )
        await self.db.commit()
        return True

    async def get_case_rarity_details(self, case_rarity_id: int):
        rarity = await self._fetchone(
            "SELECT * FROM case_rarities WHERE id = ?",
            (case_rarity_id,)
        )

        if not rarity:
            return None

        rarity_dict = dict(rarity)

        roles = await self._fetchall(
            "SELECT role_id FROM case_roles WHERE case_rarity_id = ?",
            (case_rarity_id,)
        )

        rarity_dict["roles"] = [row["role_id"] for row in roles]
        return rarity_dict

    async def update_case_rarity_settings(
        self,
        case_rarity_id: int,
        drop_chance: int = None,
        sell_price: int = None
    ) -> bool:
        rarity = await self._fetchone(
            "SELECT * FROM case_rarities WHERE id = ?",
            (case_rarity_id,)
        )

        if not rarity:
            return False

        new_chance = rarity["drop_chance"] if drop_chance is None else drop_chance
        new_sell_price = rarity["sell_price"] if sell_price is None else sell_price

        if new_chance < 0 or new_chance > 100:
            return False

        if new_sell_price < 0:
            return False

        await self.db.execute(
            """
            UPDATE case_rarities
            SET drop_chance = ?, sell_price = ?
            WHERE id = ?
            """,
            (new_chance, new_sell_price, case_rarity_id)
        )
        await self.db.commit()
        return True

    async def has_case_rarity(self, case_id: int, rarity: str) -> bool:
        row = await self._fetchone(
            """
            SELECT COUNT(*) AS count
            FROM case_rarities
            WHERE case_id = ? AND rarity = ?
            """,
            (case_id, rarity)
        )

        return bool(row and row["count"] > 0)

    async def delete_case(self, case_id: int) -> bool:
        rarities = await self._fetchall(
            "SELECT id FROM case_rarities WHERE case_id = ?",
            (case_id,)
        )

        for rarity in rarities:
            await self.db.execute(
                "DELETE FROM case_roles WHERE case_rarity_id = ?",
                (rarity["id"],)
            )

        await self.db.execute(
            "DELETE FROM case_rarities WHERE case_id = ?",
            (case_id,)
        )

        await self.db.execute(
            "DELETE FROM player_keys WHERE case_id = ?",
            (case_id,)
        )

        await self.db.execute(
            "DELETE FROM player_cases WHERE case_id = ?",
            (case_id,)
        )

        async with self.db.execute(
            "DELETE FROM cases WHERE id = ?",
            (case_id,)
        ) as cursor:
            await self.db.commit()
            return cursor.rowcount > 0

    # ===== Ключи и кейсы игроков =====

    async def add_key(self, user_id: int, guild_id: int, case_id: int, quantity: int = 1):
        from modules.shared import MAX_PLAYER_KEYS

        row = await self._fetchone(
            "SELECT quantity FROM player_keys WHERE user_id = ? AND guild_id = ? AND case_id = ?",
            (user_id, guild_id, case_id)
        )

        current = row["quantity"] if row else 0
        allowed = max(0, min(int(quantity), MAX_PLAYER_KEYS - current))

        if allowed <= 0:
            return False

        if row:
            await self.db.execute(
                """
                UPDATE player_keys
                SET quantity = quantity + ?
                WHERE user_id = ? AND guild_id = ? AND case_id = ?
                """,
                (allowed, user_id, guild_id, case_id)
            )
        else:
            await self.db.execute(
                """
                INSERT INTO player_keys (user_id, guild_id, case_id, quantity)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, guild_id, case_id, allowed)
            )

        await self.db.commit()
        return True

    async def add_case(self, user_id: int, guild_id: int, case_id: int, quantity: int = 1):
        from modules.shared import MAX_PLAYER_CASES

        row = await self._fetchone(
            "SELECT quantity FROM player_cases WHERE user_id = ? AND guild_id = ? AND case_id = ?",
            (user_id, guild_id, case_id)
        )

        current = row["quantity"] if row else 0
        allowed = max(0, min(int(quantity), MAX_PLAYER_CASES - current))

        if allowed <= 0:
            return False

        if row:
            await self.db.execute(
                """
                UPDATE player_cases
                SET quantity = quantity + ?
                WHERE user_id = ? AND guild_id = ? AND case_id = ?
                """,
                (allowed, user_id, guild_id, case_id)
            )
        else:
            await self.db.execute(
                """
                INSERT INTO player_cases (user_id, guild_id, case_id, quantity)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, guild_id, case_id, allowed)
            )

        await self.db.commit()
        return True

    async def use_key(self, user_id: int, guild_id: int, case_id: int) -> bool:
        async with self.db.execute(
            """
            UPDATE player_keys
            SET quantity = quantity - 1
            WHERE user_id = ? AND guild_id = ? AND case_id = ? AND quantity > 0
            """,
            (user_id, guild_id, case_id)
        ) as cursor:
            await self.db.commit()
            return cursor.rowcount > 0

    async def use_case(self, user_id: int, guild_id: int, case_id: int) -> bool:
        async with self.db.execute(
            """
            UPDATE player_cases
            SET quantity = quantity - 1
            WHERE user_id = ? AND guild_id = ? AND case_id = ? AND quantity > 0
            """,
            (user_id, guild_id, case_id)
        ) as cursor:
            await self.db.commit()
            return cursor.rowcount > 0

    async def get_player_key_quantity(self, user_id: int, guild_id: int, case_id: int) -> int:
        row = await self._fetchone(
            "SELECT quantity FROM player_keys WHERE user_id = ? AND guild_id = ? AND case_id = ?",
            (user_id, guild_id, case_id)
        )
        return row["quantity"] if row else 0

    async def get_player_case_quantity(self, user_id: int, guild_id: int, case_id: int) -> int:
        row = await self._fetchone(
            "SELECT quantity FROM player_cases WHERE user_id = ? AND guild_id = ? AND case_id = ?",
            (user_id, guild_id, case_id)
        )
        return row["quantity"] if row else 0

    async def get_random_role_from_case(self, case_id: int, luck_bonus: int = 0) -> Optional[Dict[str, Any]]:
        case_details = await self.get_case_details(case_id)

        if not case_details:
            return None

        rarities = [
            rarity for rarity in case_details["rarities"]
            if rarity["roles"]
        ]

        if not rarities:
            return None

        # «Удача» (бессрочное улучшение): +1% к весу каждой редкости выше common за уровень.
        order = ["common", "uncommon", "rare", "epic", "legendary", "secret", "secret+"]
        weights = []
        for rarity in rarities:
            w = max(0.0, float(rarity["drop_chance"]))
            if luck_bonus > 0 and rarity["rarity"] in order[2:]:
                w *= 1.0 + luck_bonus / 100.0
            weights.append(w)

        if sum(weights) <= 0:
            return None

        selected_rarity = random.choices(rarities, weights=weights, k=1)[0]

        return {
            "rarity": selected_rarity["rarity"],
            "role_id": random.choice(selected_rarity["roles"]),
            "market_price": selected_rarity["sell_price"]
        }

    async def open_case(self, user_id: int, guild_id: int, case_id: int) -> Dict[str, Any]:
        case_details = await self.get_case_details(case_id)

        if not case_details:
            return {"success": False, "error": "Кейс не найден."}

        if case_details["guild_id"] != guild_id:
            return {"success": False, "error": "Кейс не найден."}

        if not case_details["is_active"]:
            return {"success": False, "error": "Кейс не активен."}

        case_amount = await self.get_player_case_quantity(user_id, guild_id, case_id)
        key_amount = await self.get_player_key_quantity(user_id, guild_id, case_id)

        if case_amount < 1:
            return {"success": False, "error": "У тебя нет этого кейса."}

        if key_amount < 1:
            return {"success": False, "error": "У тебя нет ключа для этого кейса."}

        luck_level = await self.get_upgradeable_role_level(user_id, guild_id, "luck")
        if await self.has_effect(user_id, guild_id, "luck_charm"):
            luck_level += 10  # эффект «Талисман удачи»: +10% к редким на 1 час
        reward = await self.get_random_role_from_case(case_id, luck_bonus=luck_level)

        if not reward:
            return {"success": False, "error": "В кейсе нет доступных ролей."}

        if not await self.use_case(user_id, guild_id, case_id):
            return {"success": False, "error": "Не удалось использовать кейс."}

        if not await self.use_key(user_id, guild_id, case_id):
            await self.add_case(user_id, guild_id, case_id, 1)
            return {"success": False, "error": "Не удалось использовать ключ."}

        # Записываем историю открытия (для вкладок «Кейсы»/статистики в инвентаре)
        await self.db.execute(
            """
            INSERT INTO case_open_history (user_id, guild_id, case_id, role_id, rarity)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, guild_id, case_id, reward["role_id"], reward["rarity"])
        )
        await self.db.commit()

        # Дебафф «Кривая рука»: 25% шанс, если нет эффекта-щита
        debuff_applied = False
        has_shield = await self.has_effect(user_id, guild_id, "shield")

        if not has_shield and random.random() < 0.25:
            debuff_result = await self.add_debuff_to_inventory(user_id, guild_id, "clumsy_hands")

            if debuff_result != -1:
                await self.update_broken_key_cost(user_id, guild_id, case_details["key_price"])
                debuff_applied = True

        async with self.db.execute(
            """
            SELECT COUNT(*) AS count
            FROM inventory
            WHERE user_id = ? AND guild_id = ? AND role_id = ?
            """,
            (user_id, guild_id, reward["role_id"])
        ) as cursor:
            row = await cursor.fetchone()
            duplicate = bool(row and row["count"] > 0)

        inventory_id = await self.add_role_to_inventory(
            user_id,
            guild_id,
            reward["role_id"],
            "visual",
            reward["rarity"],
            1,
            reward["market_price"]
        )

        if inventory_id == -1:
            return {"success": False, "error": "Не удалось выдать роль."}

        return {
            "success": True,
            "duplicate": duplicate,
            "debuff_applied": debuff_applied,
            "rarity": reward["rarity"],
            "role_id": reward["role_id"],
            "market_price": reward["market_price"],
            "case_name": case_details["name"]
        }

    # ===== Маркетплейс =====

    async def list_role_for_sale(
        self,
        seller_id: int,
        guild_id: int,
        inventory_id: int,
        price: int,
        currency: str = "coins"
    ) -> Dict[str, Any]:
        if price <= 0:
            return {"success": False, "error": "Цена должна быть больше 0."}

        if currency not in ("coins", "crystals"):
            return {"success": False, "error": "Неверная валюта."}

        item = await self.get_inventory_item(inventory_id, seller_id, guild_id)

        if not item:
            return {"success": False, "error": "Роль не найдена в твоём инвентаре."}

        if item["role_type"] == "debuff":
            return {"success": False, "error": "Дебаффы нельзя продавать."}

        if await self.is_inventory_locked(inventory_id):
            return {"success": False, "error": "Роль уже участвует в рынке или аукционе."}

        market_price = item.get("market_price", 0) or 0
        min_price = market_price if market_price > 0 else 1

        if price < min_price:
            return {
                "success": False,
                "error": f"Нельзя выставить дешевле рыночной цены. Минимум: {min_price} монет."
            }

        was_applied = bool(item["is_applied"])

        if was_applied:
            await self.unapply_role(seller_id, guild_id, inventory_id)

        async with self.db.execute(
            """
            INSERT INTO market_listings (seller_id, guild_id, inventory_id, price, currency)
            VALUES (?, ?, ?, ?, ?)
            """,
            (seller_id, guild_id, inventory_id, price, currency)
        ) as cursor:
            await self.db.commit()
            listing_id = cursor.lastrowid

        return {
            "success": True,
            "listing_id": listing_id,
            "was_applied": was_applied,
            "role_id": item["role_id"],
            "market_price": market_price
        }

    async def get_market_listings(self, guild_id: int):
        return await self._fetchall(
            """
            SELECT ml.id, ml.seller_id, ml.guild_id, ml.inventory_id, ml.price, ml.listed_at,
                   i.role_id, i.rarity
            FROM market_listings ml
            JOIN inventory i ON ml.inventory_id = i.id
            WHERE ml.guild_id = ? AND ml.is_sold = 0
            ORDER BY ml.listed_at DESC
            """,
            (guild_id,)
        )

    async def buy_from_market(self, buyer_id: int, listing_id: int) -> Dict[str, Any]:
        listing = await self._fetchone(
            "SELECT * FROM market_listings WHERE id = ?",
            (listing_id,)
        )

        if not listing or listing["is_sold"]:
            return {"success": False, "error": "Лот не найден или уже продан."}

        currency = listing.get("currency", "coins") or "coins"

        item = await self.get_inventory_item(
            listing["inventory_id"],
            listing["seller_id"],
            listing["guild_id"]
        )

        if not item:
            return {"success": False, "error": "Роль уже недоступна."}

        if listing["seller_id"] == buyer_id:
            return {"success": False, "error": "Нельзя купить свою собственную роль."}

        await self.get_or_create_user(buyer_id, listing["guild_id"])
        await self.get_or_create_user(listing["seller_id"], listing["guild_id"])

        if not await self.try_spend(buyer_id, listing["guild_id"], listing["price"], currency):
            return {
                "success": False,
                "error": "Недостаточно кристаллов." if currency == "crystals" else "Недостаточно монет."
            }

        async with self.db.execute(
            "UPDATE market_listings SET is_sold = 1 WHERE id = ? AND is_sold = 0",
            (listing_id,)
        ) as cursor:
            if cursor.rowcount == 0:
                await self.award_currency(buyer_id, listing["guild_id"], listing["price"], currency)
                await self.db.commit()
                return {"success": False, "error": "Лот уже продан."}

        commission = int(listing["price"] * 0.05)
        seller_revenue = listing["price"] - commission

        await self.award_currency(
            listing["seller_id"], listing["guild_id"], seller_revenue, currency
        )

        was_applied = bool(item["is_applied"])

        await self.db.execute(
            "UPDATE inventory SET user_id = ?, is_applied = 0 WHERE id = ?",
            (buyer_id, listing["inventory_id"])
        )
        await self.db.commit()

        return {
            "success": True,
            "listing": listing,
            "commission": commission,
            "seller_revenue": seller_revenue,
            "was_applied": was_applied,
            "role_id": item["role_id"],
            "currency": currency
        }

    async def cancel_market_listing(self, seller_id: int, listing_id: int) -> bool:
        async with self.db.execute(
            """
            UPDATE market_listings
            SET is_sold = 1
            WHERE id = ? AND seller_id = ? AND is_sold = 0
            """,
            (listing_id, seller_id)
        ) as cursor:
            await self.db.commit()
            return cursor.rowcount > 0

    # ===== Аукционы =====

    async def create_auction(
        self,
        seller_id: int,
        guild_id: int,
        inventory_id: int,
        start_price: int,
        duration_hours: int
    ) -> Dict[str, Any]:
        if start_price < 0:
            return {"success": False, "error": "Начальная цена не может быть отрицательной."}

        if duration_hours <= 0 or duration_hours > 24:
            return {"success": False, "error": "Длительность должна быть от 1 до 24 часов."}

        item = await self.get_inventory_item(inventory_id, seller_id, guild_id)

        if not item:
            return {"success": False, "error": "Роль не найдена в твоём инвентаре."}

        if item["role_type"] == "debuff":
            return {"success": False, "error": "Дебаффы нельзя выставлять на аукцион."}

        if await self.is_inventory_locked(inventory_id):
            return {"success": False, "error": "Роль уже участвует в рынке или аукционе."}

        was_applied = bool(item["is_applied"])

        if was_applied:
            await self.unapply_role(seller_id, guild_id, inventory_id)

        end_time = int((datetime.now() + timedelta(hours=duration_hours)).timestamp())

        async with self.db.execute(
            """
            INSERT INTO auctions
            (seller_id, guild_id, inventory_id, start_price, end_time)
            VALUES (?, ?, ?, ?, ?)
            """,
            (seller_id, guild_id, inventory_id, start_price, end_time)
        ) as cursor:
            await self.db.commit()
            auction_id = cursor.lastrowid

        return {
            "success": True,
            "auction_id": auction_id,
            "was_applied": was_applied,
            "role_id": item["role_id"]
        }

    async def place_bid(self, bidder_id: int, auction_id: int, bid_amount: int) -> Dict[str, Any]:
        auction = await self._fetchone(
            "SELECT * FROM auctions WHERE id = ?",
            (auction_id,)
        )

        if not auction:
            return {"success": False, "error": "Аукцион не найден."}

        now = int(datetime.now().timestamp())

        if now >= auction["end_time"]:
            return {"success": False, "error": "Аукцион завершён."}

        if auction["seller_id"] == bidder_id:
            return {"success": False, "error": "Нельзя делать ставку на свой аукцион."}

        current_bid = auction["current_bid"] or 0
        # при нулевой стартовой цене первая ставка — минимум 1 монета
        min_bid = max(1, auction["start_price"]) if current_bid <= 0 else current_bid + 100

        if bid_amount < min_bid:
            return {"success": False, "error": f"Минимальная ставка: {min_bid} монет."}

        await self.get_or_create_user(bidder_id, auction["guild_id"])

        if not await self.try_spend_coins(bidder_id, auction["guild_id"], bid_amount):
            return {"success": False, "error": "Недостаточно монет."}

        if current_bid > 0 and auction["highest_bidder"]:
            await self.update_coins(auction["highest_bidder"], auction["guild_id"], current_bid)

        await self.db.execute(
            """
            UPDATE auctions
            SET current_bid = ?, highest_bidder = ?
            WHERE id = ?
            """,
            (bid_amount, bidder_id, auction_id)
        )
        await self.db.commit()

        return {"success": True, "bid_amount": bid_amount}

    async def get_active_auctions(self, guild_id: int):
        now = int(datetime.now().timestamp())

        return await self._fetchall(
            """
            SELECT a.*, i.role_id, i.rarity
            FROM auctions a
            JOIN inventory i ON a.inventory_id = i.id
            WHERE a.guild_id = ? AND a.end_time > ?
            ORDER BY a.end_time ASC
            """,
            (guild_id, now)
        )

    async def finalize_auction(self, auction_id: int) -> bool:
        """Завершить аукцион: продать роль победителю или вернуть продавцу."""
        auction = await self._fetchone("SELECT * FROM auctions WHERE id = ?", (auction_id,))
        if not auction or int(datetime.now().timestamp()) < auction["end_time"]:
            return False

        item = await self._fetchone(
            "SELECT * FROM inventory WHERE id = ?", (auction["inventory_id"],)
        )

        if auction["highest_bidder"] and auction["current_bid"] and item:
            # Победитель получает роль, монеты удержаны при ставке — списывать повторно не нужно.
            await self.db.execute(
                "UPDATE inventory SET user_id = ?, is_applied = 0 WHERE id = ?",
                (auction["highest_bidder"], auction["inventory_id"])
            )
        elif item:
            # Ставок не было — снимаем блокировку, роль остаётся у продавца.
            await self.db.execute(
                "UPDATE inventory SET is_applied = 0 WHERE id = ? AND is_applied = 2",
                (auction["inventory_id"],)
            )

        await self.db.execute("DELETE FROM auctions WHERE id = ?", (auction_id,))
        await self.db.commit()
        return True

    async def get_finished_auctions(self):
        now = int(datetime.now().timestamp())
        return await self._fetchall(
            "SELECT * FROM auctions WHERE end_time <= ?", (now,)
        )

    # ===== Прокачиваемые роли и дебаффы =====

    async def get_upgradeable_role_level(self, user_id: int, guild_id: int, role_type: str) -> int:
        row = await self._fetchone(
            """
            SELECT MAX(level) AS max_level
            FROM inventory
            WHERE user_id = ? AND guild_id = ? AND role_type = 'upgradeable' AND rarity = ?
            """,
            (user_id, guild_id, role_type)
        )

        return row["max_level"] if row and row["max_level"] else 0

    async def buy_upgradeable_role(
        self,
        user_id: int,
        guild_id: int,
        role_type: str,
        level: int,
        price: int
    ) -> bool:
        await self.get_or_create_user(user_id, guild_id)

        if not await self.try_spend_coins(user_id, guild_id, price):
            return False

        await self.db.execute(
            """
            DELETE FROM inventory
            WHERE user_id = ? AND guild_id = ? AND role_type = 'upgradeable' AND rarity = ?
            """,
            (user_id, guild_id, role_type)
        )

        role_id = 0

        if role_type == "rich":
            role_id = 1
        elif role_type not in ("luck", "rich"):
            role_id = 2

        await self.add_role_to_inventory(
            user_id,
            guild_id,
            role_id,
            "upgradeable",
            role_type,
            level,
            0
        )

        await self.db.commit()
        return True

    async def has_debuff(self, user_id: int, guild_id: int, debuff_type: str) -> bool:
        row = await self._fetchone(
            """
            SELECT COUNT(*) AS count
            FROM inventory
            WHERE user_id = ? AND guild_id = ? AND role_type = 'debuff'
              AND rarity = ? AND is_applied = 1
            """,
            (user_id, guild_id, debuff_type)
        )

        return bool(row and row["count"] > 0)

    async def add_debuff_to_inventory(self, user_id: int, guild_id: int, debuff_type: str) -> int:
        if await self.has_debuff(user_id, guild_id, debuff_type):
            return -1

        try:
            async with self.db.execute(
                """
                INSERT INTO inventory
                (user_id, guild_id, role_id, role_type, rarity, level, is_applied, market_price)
                VALUES (?, ?, 1000, 'debuff', ?, 1, 1, 0)
                """,
                (user_id, guild_id, debuff_type)
            ) as cursor:
                await self.db.commit()
                return cursor.lastrowid
        except aiosqlite.IntegrityError:
            return -1

    async def remove_debuff(self, user_id: int, guild_id: int, debuff_type: str):
        await self.db.execute(
            """
            DELETE FROM inventory
            WHERE user_id = ? AND guild_id = ? AND role_type = 'debuff' AND rarity = ?
            """,
            (user_id, guild_id, debuff_type)
        )
        await self.db.commit()

    # ===== Подарки =====

    async def gift_role(
        self,
        sender_id: int,
        receiver_id: int,
        guild_id: int,
        inventory_id: int
    ) -> Dict[str, Any]:
        if sender_id == receiver_id:
            return {"success": False, "error": "Нельзя подарить роль самому себе."}

        item = await self.get_inventory_item(inventory_id, sender_id, guild_id)

        if not item:
            return {"success": False, "error": "Роль не найдена."}

        if item["role_type"] != "visual":
            return {"success": False, "error": "Подарить можно только визуальные роли."}

        if await self.is_inventory_locked(inventory_id):
            return {"success": False, "error": "Роль участвует в рынке или аукционе."}

        was_applied = bool(item["is_applied"])

        await self.db.execute(
            "UPDATE inventory SET user_id = ?, is_applied = 0 WHERE id = ?",
            (receiver_id, inventory_id)
        )
        await self.db.commit()

        return {
            "success": True,
            "was_applied": was_applied,
            "role_id": item["role_id"]
        }

    # ===== Почасовое колесо =====

    async def can_spin_wheel(self, user_id: int, guild_id: int) -> Dict[str, Any]:
        user = await self.get_or_create_user(user_id, guild_id)
        now = int(datetime.now().timestamp())

        last_spin = user["last_wheel_time"]
        cooldown = 3600

        if now - last_spin < cooldown:
            return {
                "can_spin": False,
                "time_left": cooldown - (now - last_spin),
                "pity": user["wheel_pity"]
            }

        return {
            "can_spin": True,
            "time_left": 0,
            "pity": user["wheel_pity"]
        }

    async def get_player_wealth(self, user_id: int, guild_id: int) -> int:
        user = await self.get_or_create_user(user_id, guild_id)
        wealth = user["coins"]

        items = await self._fetchall(
            "SELECT role_type, rarity, level FROM inventory WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        )

        rarity_prices = {
            "common": 200,
            "uncommon": 800,
            "rare": 2000,
            "epic": 5000,
            "legendary": 15000,
            "secret": 50000,
            "secret+": 200000
        }

        for item in items:
            if item["role_type"] == "upgradeable":
                wealth += 500 * max(1, item["level"])
            else:
                wealth += rarity_prices.get(item["rarity"], 200)

        return wealth

    async def get_max_bet(self, user_id: int, guild_id: int) -> int:
        wealth = await self.get_player_wealth(user_id, guild_id)
        wealth_limit = int(wealth * 0.10)

        items = await self._fetchall(
            "SELECT rarity FROM inventory WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        )

        rarity_order = ["common", "uncommon", "rare", "epic", "legendary", "secret", "secret+"]
        max_rarity_index = -1

        for item in items:
            if item["rarity"] in rarity_order:
                index = rarity_order.index(item["rarity"])
                if index > max_rarity_index:
                    max_rarity_index = index

        rarity_limits = {
            "common": 100,
            "uncommon": 300,
            "rare": 1000,
            "epic": 3000,
            "legendary": 10000,
            "secret": 50000,
            "secret+": 200000
        }

        if max_rarity_index >= 0:
            highest_rarity = rarity_order[max_rarity_index]
            rarity_limit = rarity_limits[highest_rarity]
        else:
            rarity_limit = 100

        return max(0, min(wealth_limit, rarity_limit))


db = Database()
