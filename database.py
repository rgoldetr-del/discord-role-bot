# database.py
# Полная рабочая база данных.
# Если твой main.py импортирует database_addons и database_addons_extra,
# используй пустые файлы-заглушки ниже, либо убери эти импорты из main.py.

import random
import aiosqlite

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

DB_PATH = "bot_database.db"


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
        key_price: int
    ) -> int:
        """Создать кейс и вернуть его ID."""
        async with self.db.execute(
            """
            INSERT INTO cases (guild_id, name, case_rarity, case_price, key_price, is_active)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (guild_id, name, case_rarity, case_price, key_price)
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
                obtained_at INTEGER DEFAULT (strftime('%s', 'now'))
            );

            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                case_rarity TEXT NOT NULL,
                case_price INTEGER NOT NULL,
                key_price INTEGER NOT NULL,
                is_active INTEGER DEFAULT 0,
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
        key_price: int = None
    ) -> bool:
        case = await self._fetchone("SELECT * FROM cases WHERE id = ?", (case_id,))

        if not case:
            return False

        new_name = case["name"] if name is None else name.strip()
        new_case_price = case["case_price"] if case_price is None else case_price
        new_key_price = case["key_price"] if key_price is None else key_price

        if not new_name:
            return False

        if new_case_price < 0 or new_key_price < 0:
            return False

        await self.db.execute(
            """
            UPDATE cases
            SET name = ?, case_price = ?, key_price = ?
            WHERE id = ?
            """,
            (new_name, new_case_price, new_key_price, case_id)
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
        from modules.economy_utils import MAX_PLAYER_KEYS

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
        from modules.economy_utils import MAX_PLAYER_CASES

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

    async def get_random_role_from_case(self, case_id: int) -> Optional[Dict[str, Any]]:
        case_details = await self.get_case_details(case_id)

        if not case_details:
            return None

        rarities = [
            rarity for rarity in case_details["rarities"]
            if rarity["roles"]
        ]

        if not rarities:
            return None

        weights = [max(0, float(rarity["drop_chance"])) for rarity in rarities]

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

        reward = await self.get_random_role_from_case(case_id)

        if not reward:
            return {"success": False, "error": "В кейсе нет доступных ролей."}

        if not await self.use_case(user_id, guild_id, case_id):
            return {"success": False, "error": "Не удалось использовать кейс."}

        if not await self.use_key(user_id, guild_id, case_id):
            await self.add_case(user_id, guild_id, case_id, 1)
            return {"success": False, "error": "Не удалось использовать ключ."}

        debuff_applied = False

        if random.random() < 0.05:
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
        price: int
    ) -> Dict[str, Any]:
        if price <= 0:
            return {"success": False, "error": "Цена должна быть больше 0."}

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
            INSERT INTO market_listings (seller_id, guild_id, inventory_id, price)
            VALUES (?, ?, ?, ?)
            """,
            (seller_id, guild_id, inventory_id, price)
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

        if not await self.try_spend_coins(buyer_id, listing["guild_id"], listing["price"]):
            return {"success": False, "error": "Недостаточно монет."}

        async with self.db.execute(
            "UPDATE market_listings SET is_sold = 1 WHERE id = ? AND is_sold = 0",
            (listing_id,)
        ) as cursor:
            if cursor.rowcount == 0:
                await self.update_coins(buyer_id, listing["guild_id"], listing["price"])
                await self.db.commit()
                return {"success": False, "error": "Лот уже продан."}

        commission = int(listing["price"] * 0.05)
        seller_revenue = listing["price"] - commission

        await self.update_coins(listing["seller_id"], listing["guild_id"], seller_revenue)

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
            "role_id": item["role_id"]
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
        if start_price <= 0:
            return {"success": False, "error": "Начальная цена должна быть больше 0."}

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
        min_bid = auction["start_price"] if current_bid <= 0 else current_bid + 100

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
