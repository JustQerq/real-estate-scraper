import json
import os
import unicodedata
import random
import asyncio
import logging
from playwright_stealth import Stealth
from playwright.async_api import Page, async_playwright
from urllib.parse import urljoin
from dotenv import load_dotenv
from bs4 import BeautifulSoup


load_dotenv()
DEBUG_MODE = True
logger = logging.getLogger(__name__)

BASE_URL = os.getenv("BASE_URL")
RENT_PATH = os.getenv("RENT_PATH")



def process_page(
    soup: BeautifulSoup,
    existing_ids: set[int],
    stop_on_seen: bool = False
):
    """
    Extracts item data from a soup object

    Args:
        soup (BeautifulSoup): Soup object containing page data

    Returns:
        list[dict]: _description_
    """
    items_processed = []
    new_ids = set[int]()

    items = soup.find_all("div", class_="product-item")
    if len(items) == 0:
        raise Exception("No items found on the page, aborting.")
        
    if DEBUG_MODE: 
        logger.info(f"Successfully loaded {len(items)} items.")
    
    for item in items:
        item_processed = {}
        
        data_id = item.get('data-id')

        if not data_id:
            continue
        if isinstance(data_id, str):
            try:
                data_id = int(data_id)
            except:
                logger.warning(f"Could not convert item ID '{data_id}' to int")
                continue
        else:
            continue

        if data_id in existing_ids and stop_on_seen:
            return True, items_processed, new_ids
        
        item_processed['data-id'] = data_id
        item_processed['href_visited'] = False
        new_ids.add(data_id)
        
        item_title_container = item.find('h3', class_="product-title")
        if item_title_container:
            item_link = item_title_container.find("a")
            if item_link:
                item_processed['href'] = item_link['href']
                item_processed['title'] = item_link.get_text()
        
        price_container = item.find('div', class_="central-feature")
        if price_container:
            price_field = price_container.find('span')
            if price_field:
                price = price_field['data-value']
                if isinstance(price, str):
                    item_processed['price'] = price.replace(".", "")
        
        location_container = item.find('ul', class_="subtitle-places")
        locations = list(location_container.find_all('li')) if location_container else []
        if len(locations) > 0:
            item_processed["city"] = unicodedata.normalize('NFKC', locations[0].get_text()).strip()
            if len(locations) > 1:
                item_processed["district"] = unicodedata.normalize('NFKC', locations[1].get_text()).strip()
                if len(locations) > 2:
                    item_processed["microdistrict"] = unicodedata.normalize('NFKC', locations[2].get_text()).strip()
                    if len(locations) > 3:
                        item_processed["street"] = unicodedata.normalize('NFKC', locations[3].get_text()).strip()

        
        features = item.find_all('div', class_="value-wrapper")
        if features:
            if len(features) > 0:
                area = features[0].find(string=True)
                if area:
                    item_processed['area'] = unicodedata.normalize('NFKC', area).strip().split()[0]
                if len(features) > 1:
                    rooms = features[1].find(string=True)
                    if rooms:
                        item_processed['rooms'] = unicodedata.normalize('NFKC', rooms).strip()
                    if len(features) > 2:
                        floors = features[2].find(string=True)
                        if floors:
                            floor_data = unicodedata.normalize('NFKC', floors).strip().split("/")
                            if len(floor_data) > 0:
                                item_processed['floor'] = floor_data[0]
                                if len(floor_data) > 1:
                                    item_processed['max_floors'] = floor_data[1]
        
        description = item.find('p', class_="short-desc")
        if description:
            item_processed['description'] = description.text
        
        items_processed.append(item_processed)
    
    return False, items_processed, new_ids


async def goto_with_backoff(page: Page, url: str, retries=4):
    delay = 60
    for attempt in range(retries):
        response = await page.goto(url)
        if response and response.status in (403, 429, 503):
            await asyncio.sleep(delay)
            delay *= 2
        else:
            return response
    raise Exception(f"Failed after {retries} retries: {url}")


async def scrape_pages(
    n_pages: int = 1, 
    starting_page: int = 1,
    stop_on_seen: bool = True,
    existing_ids: set[int] | None = None
):
    if not BASE_URL:
        raise Exception("BASE_URL variable not found in environment")
    if not RENT_PATH:
        raise Exception("RENT_PATH variable not found in environment")
    
    RENT_URL = urljoin(BASE_URL, RENT_PATH)

    if not existing_ids:
        existing_ids = set[int]()

    async with Stealth().use_async(async_playwright()) as p:
        # Using headless=False to appear more human-like
        browser = await p.chromium.launch(headless=False, args=['--start-maximized'])
        page = await browser.new_page()
        await page.set_viewport_size({"width": 1920, "height": 1080})
        await page.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": BASE_URL,
            "DNT": "1"
        })

        items_processed = []
        page_number = starting_page
        pages_counter = 0

        try:
            while pages_counter < n_pages:
                await goto_with_backoff(page, urljoin(RENT_URL, f"?page={page_number}"))
                await page.wait_for_load_state("domcontentloaded")

                element = page.locator(".product-item").last
                await element.wait_for(timeout=10000)
                box = await element.bounding_box()
                if box:
                    # Move mouse to a random point within the element
                    x = box["x"] + box["width"] * random.random()
                    y = box["y"] + box["height"] * random.random()
                    await page.mouse.move(x, y, steps=random.randint(5, 15)) # Smooth movement
                    await asyncio.sleep(random.uniform(0.5, 1.5)) # Random delay after click
                
                # Extract the fully rendered HTML source
                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")
                existing_id_found, processed_page_items, new_ids = process_page(soup, existing_ids, stop_on_seen)
                items_processed.extend(processed_page_items)
                existing_ids.update(new_ids)

                if stop_on_seen and existing_id_found:
                    logger.info(f"Found existing item id, stopping early on page {page_number}")
                    break
                
                page_number += 1
                pages_counter += 1
                logger.info(f"Processed {pages_counter} pages.")
                if pages_counter < n_pages:
                    if pages_counter % 25 == 0:
                        sleep_time = random.uniform(120, 300)
                        logger.info(f"Sleeping for a longer interval of {sleep_time} seconds between pages.")
                        await asyncio.sleep(sleep_time)
                    else:
                        sleep_time = random.uniform(3, 8)
                        logger.info(f"Sleeping for an interval of {sleep_time} seconds between pages.")
                        await asyncio.sleep(sleep_time)
            
            logger.info(f"Successfully scraped all pages")
            
        except Exception as e:
            logger.error(f"Error during scrape: {e}")
            logger.info("Writing last page's content to 'broken_page.html'.")
            with open("broken_page.html", "w", encoding="utf8") as f:
                f.write(await page.content())
            
        finally:
            await browser.close()
    
    return items_processed