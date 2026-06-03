import os
import time
import unicodedata
import random
import logging
from playwright_stealth import Stealth
from playwright.async_api import async_playwright
from urllib.parse import urljoin
from dotenv import load_dotenv
from bs4 import BeautifulSoup


DEBUG_MODE = True

load_dotenv()
BASE_URL = os.getenv("BASE_URL", "")
RENT_PATH = os.getenv("RENT_PATH", "")
RENT_URL = urljoin(BASE_URL, RENT_PATH)


def process_page(soup: BeautifulSoup):
    items_processed = []
    items = soup.find_all("div", class_="product-item")
    if DEBUG_MODE: 
        print(f"Successfully loaded {len(items)} items.")
    
    for item in items:
        item_processed = {}
        
        data_id = item.get('data-id')
        if not data_id:
            continue
        item_processed['data-id'] = data_id
        
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
                item_processed['price'] = price_field['data-value']
        
        location_container = item.find('ul', class_="subtitle-places")
        locations = list(location_container.children) if location_container else []
        if len(locations) > 0:
            item_processed['locations'] = [unicodedata.normalize('NFKC', location.get_text()).strip() for location in locations]
        
        features = item.find_all('div', class_="value-wrapper")
        if features and len(features) == 3:
            area = features[0].find(string=True)
            if area:
                item_processed['area'] = unicodedata.normalize('NFKC', area).strip().split()[0]
            
            rooms = features[1].find(string=True)
            if rooms:
                item_processed['rooms'] = unicodedata.normalize('NFKC', rooms).strip()
                
            floors = features[2].find(string=True)
            if floors:
                floor_data = unicodedata.normalize('NFKC', floors).strip().split("/")
                if len(floor_data) == 2:
                    item_processed['floor'] = floor_data[0]
                    item_processed['max_floors'] = floor_data[1]
        
        items_processed.append(item_processed)
    
    return items_processed


async def scrape_pages(n_pages: int = 1, starting_page: int = 1):
    async with Stealth().use_async(async_playwright()) as p:
        # Using headless=False to appear more human-like
        browser = await p.chromium.launch(headless=False, args=['--start-maximized'])
        page = await browser.new_page()
        items_processed = []
        
        page_number = starting_page
        pages_counter = 0
        try:
            while pages_counter < n_pages:
                await page.goto(urljoin(RENT_URL, f"?page={page_number}"))
                await page.wait_for_load_state("domcontentloaded")
                element = page.locator(".product-item").last
                await element.wait_for(timeout=10000)
                box = await element.bounding_box()
                if box:
                    # Move mouse to a random point within the element
                    x = box["x"] + box["width"] * random.random()
                    y = box["y"] + box["height"] * random.random()
                    await page.mouse.move(x, y, steps=random.randint(5, 15)) # Smooth movement
                    time.sleep(random.uniform(0.5, 1.5)) # Random delay after click
                
                # Extract the fully rendered HTML source
                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")
                items_processed.append(process_page(soup))
                
                page_number += 1
                pages_counter += 1
            
        except Exception as e:
            print("Error: ", e)
            with open("error_page.html", "w") as f:
                f.write(await page.content())
            
        finally:
            await browser.close()
            await p.stop()
    
    return items_processed