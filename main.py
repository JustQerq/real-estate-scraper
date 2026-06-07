import json
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from database import init_database, get_rent_ids, save_rent_items
from scraper import scrape_pages


def setup_logging() -> Path:
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = logs_dir / f"run_{timestamp}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return log_file


if __name__ == "__main__":
    log_file = setup_logging()
    logger = logging.getLogger(__name__)
    logging.info("Logging to %s", log_file)
    init_database()
    
    try:
        scraped_items = asyncio.run(scrape_pages(
            n_pages=2, 
            stop_on_seen=False,
            existing_ids=get_rent_ids()
        ))
    except Exception as e:
        logger.error(f"Error occurred while scraping: {e}")
    
    try:
        save_rent_items(scraped_items)
        logger.info("Successfully saved scraped data into SQLite DB.")
    except Exception as e:
        logger.error(f"SQLite save failed, resorting to a JSON file. Error: {e}")
        with open("data.json", "w", encoding="utf8") as f:
            json.dump(scraped_items, f, indent=4, ensure_ascii=False)
        logger.info("Saved scraped data into 'data.json' file.")
