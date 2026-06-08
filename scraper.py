import os
import unicodedata
import random
import asyncio
import logging
from datetime import date
from pathlib import Path
from playwright_stealth import Stealth
from playwright.async_api import Page, BrowserContext, Playwright, async_playwright
from urllib.parse import urljoin
from dotenv import load_dotenv
from bs4 import BeautifulSoup


load_dotenv()
logger = logging.getLogger(__name__)

BASE_URL = os.getenv("BASE_URL")
RENT_PATH = os.getenv("RENT_PATH")
SESSION_PROFILE_DIR = "session-profile"
STORAGE_STATE_PATH = Path(SESSION_PROFILE_DIR) / "storage_state.json"
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"

BROWSER_ARGS = [
    "--start-maximized",
    "--disable-blink-features=AutomationControlled",
]
BROWSER_HEADERS = {
    "Accept-Language": "sr-RS,sr;q=0.9,en;q=0.8",
    "DNT": "1",
}


def process_page(
    soup: BeautifulSoup,
    existing_ids: set[int],
    stop_on_seen: bool = False,
    stop_date: date | None = None
):
    """
    Extracts item data from a soup object

    Args:
        soup (BeautifulSoup): Soup object containing page data

    Returns:
        tuple[bool, str | None, list[dict], set[int]]
    """
    items_processed = []
    new_ids = set[int]()

    items = soup.find_all("div", class_="product-item")
    if len(items) == 0:
        raise Exception("No items found on the page, aborting.")

    logger.info(f"Successfully loaded {len(items)} items.")

    for item in items:
        item_processed = {}

        data_id = item.get('data-id')
        if not data_id:
            continue
        if isinstance(data_id, str):
            try:
                data_id = int(data_id)
            except Exception as e:
                logger.warning(f"Could not convert item ID '{data_id}' to int; error: {e}")
                continue
        else:
            continue
        if data_id in existing_ids:
            if stop_on_seen:
                return True, "Found an existing item ID", items_processed, new_ids
            continue

        item_processed['data-id'] = data_id
        item_processed['href_visited'] = False
        new_ids.add(data_id)

        publish_date = item.find('span', class_="publish-date")
        if publish_date:
            publish_date = publish_date.get_text(strip=True).strip('.')
            try:
                publish_date = date.strptime(publish_date, "%d.%m.%Y")
                item_processed['publish_date'] = publish_date.isoformat()
                if stop_date and publish_date <= stop_date:
                    return True, "Date cutoff reached", items_processed, new_ids
            except Exception as e:
                logger.warning(f"Could not parse publish date '{publish_date}'; error: {e}")
                continue
        else:
            continue

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
                if price:
                    if isinstance(price, str):
                        item_processed['price'] = price.replace(".", "")
                    else:
                        try:
                            item_processed['price'] = str(price)
                        except Exception as e:
                            logger.warning(f"Could not convert price, error: {e}")

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

    return False, None, items_processed, new_ids


async def goto_with_backoff(page: Page, url: str, retries: int = 4):
    delay = 60
    for attempt in range(retries):
        response = None
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        except Exception as e:
            logger.warning(f"Navigation attempt {attempt + 1}/{retries} failed for {url}: {e}")

        if response is None or response.status in (403, 429, 503):
            status = response.status if response else "no response"
            logger.warning(f"Got {status} for {url}, retrying in {delay}s")
            await asyncio.sleep(delay)
            delay *= 2
            continue

        return response

    raise Exception(f"Failed after {retries} retries: {url}")


async def simulate_human_behavior(page: Page):
    await asyncio.sleep(random.uniform(0.5, 1.5))

    viewport = page.viewport_size or {"width": 1920, "height": 1080}
    for _ in range(random.randint(2, 4)):
        x = random.randint(80, max(80, viewport["width"] - 80))
        y = random.randint(80, max(80, viewport["height"] - 80))
        await page.mouse.move(x, y, steps=random.randint(8, 20))
        await asyncio.sleep(random.uniform(0.1, 0.4))

    for _ in range(random.randint(3, 6)):
        await page.mouse.wheel(0, random.randint(200, 600))
        await asyncio.sleep(random.uniform(0.3, 0.8))

    if random.random() < 0.3:
        await page.mouse.wheel(0, -random.randint(100, 300))
        await asyncio.sleep(random.uniform(0.2, 0.5))


async def get_active_page(context: BrowserContext) -> Page:
    if context.pages:
        return context.pages[0]
    return await context.new_page()


async def launch_browser_context(
    p: Playwright,
    *,
    headless: bool,
) -> BrowserContext:
    Path(SESSION_PROFILE_DIR).mkdir(parents=True, exist_ok=True)

    context_options = {
        "user_data_dir": SESSION_PROFILE_DIR,
        "headless": headless,
        "locale": "sr-RS",
        "timezone_id": "Europe/Belgrade",
        "viewport": {"width": 1920, "height": 1080},
        "args": BROWSER_ARGS,
        "extra_http_headers": BROWSER_HEADERS,
    }

    try:
        return await p.chromium.launch_persistent_context(channel="chrome", **context_options)
    except Exception:
        logger.warning("Installed Chrome not available, falling back to bundled Chromium")
        return await p.chromium.launch_persistent_context(**context_options)


async def save_session_state(context: BrowserContext):
    Path(SESSION_PROFILE_DIR).mkdir(parents=True, exist_ok=True)
    await context.storage_state(path=str(STORAGE_STATE_PATH))
    logger.info("Saved session state to %s", STORAGE_STATE_PATH)


async def warmup_navigation(page: Page, base_url: str):
    logger.info("Warming up session via homepage")
    await goto_with_backoff(page, base_url)
    await simulate_human_behavior(page)
    await asyncio.sleep(random.uniform(2, 4))


async def warmup_run():
    """
    Opens a headed browser with a persistent profile for manual cookie/TOS acceptance.
    Type 'quit' and press Enter when finished to save session state and exit.
    """
    if not BASE_URL:
        raise Exception("BASE_URL variable not found in environment")

    async with Stealth().use_async(async_playwright()) as p:
        context = await launch_browser_context(p, headless=False)
        page = await get_active_page(context)

        try:
            await goto_with_backoff(page, BASE_URL)  # validated above
            await simulate_human_behavior(page)
            logger.info(
                "Browser ready at %s. Accept cookies/TOS manually, browse as needed, "
                "then type 'quit' and press Enter to save and exit.",
                BASE_URL,
            )

            while True:
                command = await asyncio.to_thread(input, "> ")
                if command.strip().lower() == "quit":
                    break
        finally:
            await save_session_state(context)
            await context.close()


async def scrape_test():
    items = []
    for i in range(4):
        item = []
        for j in range(3):
            item.append(str(j*(i+1)))
        yield item
        await asyncio.sleep(2)


async def scrape_pages(
    n_pages: int = 1,
    starting_page: int = 1,
    stop_on_seen: bool = True,
    stop_date: date | None = None,
    existing_ids: set[int] | None = None
):
    if not BASE_URL:
        raise Exception("BASE_URL variable not found in environment")
    if not RENT_PATH:
        raise Exception("RENT_PATH variable not found in environment")

    rent_url = urljoin(BASE_URL, RENT_PATH)

    if not existing_ids:
        existing_ids = set[int]()

    async with Stealth().use_async(async_playwright()) as p:
        context = await launch_browser_context(p, headless=HEADLESS)
        page = await get_active_page(context)

        items_processed = []
        page_number = starting_page
        pages_counter = 0

        try:
            await warmup_navigation(page, BASE_URL)

            while pages_counter < n_pages:
                page_url = rent_url if page_number == 1 else urljoin(rent_url, f"?page={page_number}")
                await goto_with_backoff(page, page_url)
                await page.wait_for_load_state("domcontentloaded")
                await simulate_human_behavior(page)

                element = page.locator(".product-item").last
                await element.wait_for(timeout=10_000)

                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")
                early_stop, early_stop_reason, processed_page_items, new_ids = process_page(
                    soup=soup,
                    existing_ids=existing_ids,
                    stop_on_seen=stop_on_seen,
                    stop_date=stop_date,
                )
                items_processed.extend(processed_page_items)
                existing_ids.update(new_ids)

                if early_stop:
                    logger.info(f"Scraping stopped early for the following reason: {early_stop_reason}")
                    break

                page_number += 1
                pages_counter += 1
                logger.info(f"Processed {pages_counter} pages.")
                if pages_counter < n_pages:
                    if pages_counter % 25 == 0:
                        sleep_time = random.uniform(120, 300)
                        logger.info(f"Sleeping for {sleep_time} seconds between page clusters")
                        await asyncio.sleep(sleep_time)
                    else:
                        sleep_time = random.uniform(3, 8)
                        logger.info(f"Sleeping for {sleep_time} seconds between pages")
                        await asyncio.sleep(sleep_time)

            logger.info("Successfully finished scraping")

        except Exception as e:
            logger.error(f"Error during scrape: {e}")
            logger.info("Writing last page's content to 'broken_page.html'")
            with open("broken_page.html", "w", encoding="utf8") as f:
                f.write(await page.content())

        finally:
            await save_session_state(context)
            await context.close()

    return items_processed