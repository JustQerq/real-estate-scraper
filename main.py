import sys
import json
import asyncio
import logging
from datetime import datetime, date
from pathlib import Path

from database import init_database, get_rent_ids, save_rent_items
from scraper import scrape_pages, scrape_test


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


async def main(**kwargs):
    log_file = setup_logging()
    logger = logging.getLogger(__name__)
    logging.info("Logging to %s", log_file)
    init_database()

    stop_date = kwargs.get("stop-date")
    if stop_date:
        try:
            stop_date = date.strptime(stop_date, "%d.%m.%y")
        except Exception as e:
            print(f"Error parsing stop-date: {e}")
    
    pages = kwargs.get("pages")
    if pages:
        try:
            pages = int(pages)
        except:
            raise ValueError("Could not convert 'pages' argument to an integer")
    else:
        pages = 2
    

    stop_on_seen = kwargs.get("stop-on-seen")
    if stop_on_seen:
        try:
            stop_on_seen = bool(stop_on_seen)
        except:
            raise ValueError("Could not convert 'stop-on-seen' argument to boolean")
    else:
        stop_on_seen = False
    
    logger.info(f"Running with kwargs: n_pages={pages}, stop_date={stop_date}, stop_on_seen={stop_on_seen}")
    
    try:
        scraped_items = asyncio.run(scrape_pages(
            n_pages=pages, 
            stop_on_seen=stop_on_seen,
            stop_date=stop_date,
            existing_ids=get_rent_ids()
        ))
    except Exception as e:
        logger.error(f"Error occurred while scraping: {e}")
    
    if scraped_items:
        if len(scraped_items) > 0:
            try:
                save_rent_items(scraped_items)
                logger.info("Successfully saved scraped data into SQLite DB.")
            except Exception as e:
                logger.error(f"SQLite save failed, resorting to a JSON file. Error: {e}")
                with open(f"data_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.json", "w", encoding="utf8") as f:
                    json.dump(scraped_items, f, indent=4, ensure_ascii=False)
                logger.info("Saved scraped data into 'data.json' file.")
        else:
            logger.info("No new items to save")
    else:
        logger.info("Error occurred during scraping, nothing to save")


if __name__ == "__main__":
    script_kwargs = {}
    for arg in sys.argv[1:]:
        if "=" in arg:
            key, value = arg.split("=", 1)
            script_kwargs[key] = value
    
    asyncio.run(main(**script_kwargs))