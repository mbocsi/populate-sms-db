import os
import mysql.connector as mysql
from dotenv import load_dotenv
from dataclasses import dataclass
import requests
from time import sleep
import logging
from bs4 import BeautifulSoup

load_dotenv()
logging.basicConfig(level=logging.INFO, filename="main.log", encoding="utf-8", format="%(asctime)s %(message)s" )

DB_HOST = os.getenv("DB_HOST")
DB_USERNAME = os.getenv("DB_USERNAME")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_DATABASE = os.getenv("DB_DATABASE")

ITEMS_URL = "https://steamcommunity.com/market/search/render"
ITEM_PAGE_URL = "https://steamcommunity.com/market/listings"

@dataclass(slots=1)
class Item:
    itemNameId: int
    itemHashName: str
    itemName: str
    itemIcon: str
    gameId: int

class PopulateItems:
    def __init__(self, appId : int, start_index : int = 0, page_size : int = 100):
        try:
            self.connection = mysql.connect(host=DB_HOST, user=DB_USERNAME, password=DB_PASSWORD, database=DB_DATABASE)
            logging.info(f"Connected to database!")
        except Exception as e:
            logging.critical(f"Unable to connect to database: {e}")
            exit(1)
        self.start_index = start_index
        self.page_size = page_size
        self.appId = appId
    
    def add_item(self, data: Item) -> bool:
        logging.info(f"Adding the item to database! {data}")
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute(f"""
                        INSERT INTO Item (itemNameId, itemHashName, itemName, itemIcon, gameId)
                        VALUES ({data.itemNameId}, "{data.itemHashName}", "{data.itemName}", "{data.itemIcon}", {data.gameId})
                        """)
            cursor.close()
            return True
        except Exception as e:
            logging.exception(f"An error occured when inserting into database! -> {data}")
            return False
    
    def in_database(self, itemHashName : str) -> bool:
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute(f"SELECT COUNT(*) as num FROM Item WHERE itemHashName = \"{itemHashName}\"")
            toReturn = cursor.fetchone()['num']
            logging.debug(toReturn)
            cursor.close()
            return toReturn
        except Exception as e:
            logging.exception("An exception occured when checking for item in database!")
    
    def populate_items(self):
        while True:
            try:
                res = requests.get(ITEMS_URL, params={
                    "query": f"appid:{self.appId}",
                    "count": self.page_size,
                    "search_descriptions": 1,
                    "norender": 1,
                    "start": self.start_index
                })
                logging.debug(f"Requested {res.request}")
                if res.status_code != 200:
                    raise Exception(f"Status code for {ITEMS_URL} was {res.status_code}")
                
                res_json = res.json()
                logging.debug(f"Response JSON: {res_json}")
                if not res_json['success']:
                    raise Exception(f"Success field was false")
                
                results = res_json["results"]
                logging.info(f"Items {self.start_index} to {self.start_index + self.page_size} received")
                
                for item in results:
                    try:
                        hashName = item["hash_name"]

                        if self.in_database(hashName):
                            logging.info(f"{hashName} already in database! Skipping!")
                            continue

                        page_url = f"{ITEM_PAGE_URL}/{self.appId}/{hashName}"
                        logging.debug(f"Requesting {page_url}")
                        r = requests.get(page_url)

                        if r.status_code != 200:
                            raise Exception(f"Status code for {page_url} was {r.status_code}")
                        
                        html = r.content
                        soup = BeautifulSoup(html, 'html.parser')
                        logging.debug(f"Response content: {soup.prettify()}")
                        script = soup.find_all("script")[-1].string
                        logging.debug(f"Script content: {script}")

                        idx = script.find("Market_LoadOrderSpread")
                        script = script[idx+25:]
                        idx = script.find(")")
                        script = script[:idx]
                        script = script.strip()
                        itemNameId = int(script)
                        logging.debug(f"Found ItemNameId: {itemNameId}")

                        marketItem = Item(itemNameId, hashName, item['name'], item['asset_description']['icon_url'], item['asset_description']['appid'])
                        if not self.add_item(marketItem):
                            logging.warning("Failed to insert item into database!")
                            """Do nothing else for now, just skip"""

                        sleep(10)
                        
                    except Exception as e:
                        logging.exception(f"An error occured when doing an item market request")
                        sleep(60)



            except Exception as e:
                logging.exception(f"An error occured when doing an item batch request")
                sleep(60)
                continue
            
            if len(results) == 0: # Results is empty
                break

            self.start_index += self.page_size
        
        logging.info("Script finished!")





def main():
    itemPopulator = PopulateItems(730)
    itemPopulator.populate_items()

if __name__ == "__main__":
    main()