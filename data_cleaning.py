import os
import json
import time
import logging
from pathlib import Path
import googlemaps
import pandas as pd
from dotenv import load_dotenv
from database import load_rent_items


logger = logging.getLogger(__name__)

CACHE_FILE = Path("data/geocoding_cache.json")
cache: dict[str, dict] = {}

def load_cache():
    global cache
    cache = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}

load_cache()
load_dotenv()


def save_cache():
    CACHE_FILE.write_text(json.dumps(cache))

def geocode_place(query: str):
    if query not in cache:
        gmaps = googlemaps.Client(key=os.getenv("GEOCODING_API_KEY"))
        try:
            results = gmaps.geocode(query)
            if results:
                loc = results[0]['geometry']['location']
                return {"lat": loc['lat'], "lng": loc['lng']}
            else:
                return {"lat": float("nan"), "lng": float("nan")}
        except Exception as e:
            logger.error(f"Error geocoding place: {e}")
            return {"lat": float("nan"), "lng": float("nan")}
    
    return cache[query]

def geocode_dataframe(
    df: pd.DataFrame,
    cols: str | list[str]
):
    df_copy = df.copy()
    
    if isinstance(cols, str):
        cols = [cols]
    
    location_col = "location"
    
    if len(cols) == 1:
        location_col = cols[0]
    else:
        df_copy[location_col] = df[cols].agg(', '.join, axis=1)
    
    unique_places = df_copy[location_col].dropna().unique()
    for place in unique_places:
        cache[place] = geocode_place(place)
        time.sleep(0.05)
    
    save_cache()
    
    coords_df = pd.DataFrame.from_dict(cache, orient="index").rename_axis(location_col).reset_index()
    return df_copy.join(coords_df.set_index("location"), on="location", how="left")


def parse_floor(floor: str) -> float | None:
    specials_map = {
        'PR': 0,       # ground floor
        'VPR': 0.5,    # high ground floor 
        'SUT': -1,     # basement
        'PSUT': -0.5   # half-basement
    }

    roman_map = {
        'I': 1,
        'V': 5,
        'X': 10,
        'L': 50,
        'C': 100,
        'D': 500,
        'M': 1000
    }

    converted = specials_map.get(floor)
    if converted is None:
        try:
            total = 0
            length = len(floor)
            
            for i in range(length):
                current_value = roman_map[floor[i]]
                
                if i + 1 < length and current_value < roman_map[floor[i + 1]]:
                    total -= current_value
                else:
                    total += current_value
            
            converted = total
        except:
            converted = float("nan")
    
    return converted


def clean_rent(data: list[dict]):
    raw_df = pd.DataFrame(data)
    raw_df.drop(["href", "href_visited", "title", "street", "description", "max_floors"], axis=1, inplace=True)
    raw_df.set_index("id", drop=True, inplace=True)
    clean_df = geocode_dataframe(raw_df, cols=["city", "district", "microdistrict"])
    clean_df.dropna(inplace=True)
    clean_df.drop(["city", "district", "microdistrict", "location"], axis=1, inplace=True)
    clean_df['floor'] = clean_df['floor'].apply(parse_floor)
    clean_df.to_csv("data/data_clean.csv")


if __name__ == "__main__":
    print(geocode_place('Srbija, Beograd, Opština Vračar, Hram svetog Save, Dubljanska'))