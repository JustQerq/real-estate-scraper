import sqlite3
import json
import logging


logger = logging.getLogger(__name__)

def init_database():
    """
    Initializes the database and creates tables if not present
    """
    with sqlite3.connect("data.db") as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS rent_raw (
                id INTEGER PRIMARY KEY,
                publish_date TEXT,
                title TEXT,
                href TEXT,
                href_visited INTEGER,
                price REAL,
                city TEXT,
                district TEXT,
                microdistrict TEXT,
                street TEXT,
                floor TEXT,
                max_floors TEXT,
                area REAL,
                rooms REAL,
                description TEXT,
                advertiser TEXT,
                construction_type TEXT,
                is_furnished INTEGER,
                heating TEXT,
                payment_type TEXT,
                extra_info TEXT,
                other TEXT
            );
        """)


def get_rent_ids():
    """
    Returns a set of unique ad ids stored in the database

    Returns:
        set[int]: set of unique ad ids
    """
    with sqlite3.connect("data.db") as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("SELECT id FROM rent_raw")
        result = cur.fetchall()
        return set[int]([row["id"] for row in result])


def save_rent_items(items: list[dict]):
    with sqlite3.connect("data.db") as con:
        cur = con.cursor()
        rows = []
        for item in items:
            extra_info = item.get("extra_info")
            if isinstance(extra_info, list):
                extra_info = ", ".join(extra_info)
            
            other = item.get("other")
            if isinstance(other, list):
                other = ", ".join(other)

            href_visited = item.get("href_visited", False)
            if isinstance(href_visited, bool):
                href_visited = int(href_visited)
            
            is_furnished = item.get("is_furnished")
            if isinstance(is_furnished, bool):
                is_furnished = int(is_furnished)
            
            price = item.get("price")
            if isinstance(price, str):
                try:
                    price = float(price)
                except Exception as e:
                    logger.error(f"Could not convert price, error {e}")
                    price = None
            
            area = item.get("area")
            if isinstance(area, str):
                try:
                    area = float(area)
                except Exception as e:
                    logger.error(f"Could not convert area, error {e}")
                    area = None
            
            rooms = item.get("rooms")
            if isinstance(rooms, str):
                try:
                    rooms = float(rooms)
                except Exception as e:
                    logger.error(f"Could not convert rooms, error {e}")
                    rooms = None

            rows.append((
                item["data-id"],
                item.get("publish_date"),
                item.get("title"),
                item.get("href"),
                href_visited,
                price,
                item.get("city"),
                item.get("district"),
                item.get("microdistrict"),
                item.get("street"),
                item.get("floor"),
                item.get("max_floors"),
                area,
                rooms,
                item.get("description"),
                item.get("advertiser"),
                item.get("construction_type"),
                is_furnished,
                item.get("heating"),
                item.get("payment_type"),
                extra_info,
                other,
            ))

        cur.executemany("""
            INSERT INTO rent_raw (
                id, publish_date, title, href, href_visited, price,
                city, district, microdistrict, street,
                floor, max_floors, area, rooms, description,
                advertiser, construction_type, is_furnished,
                heating, payment_type, extra_info, other
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id)
            DO NOTHING;
        """, rows)
        logger.info(f"Inserted {cur.rowcount} out of {len(rows)}")
        con.commit()
