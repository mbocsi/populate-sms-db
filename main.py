import os
import mysql.connector
from dotenv import load_dotenv
from dataclasses import dataclass
import requests
from time import sleep
import logging

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_USERNAME = os.getenv("DB_USERNAME")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_DATABASE = os.getenv("DB_DATABASE")

ITEMS_URL = "https://steamcommunity.com/market/search/render/"

@dataclass(slots=1)
class Item:
    itemNameId: int
    itemHashName: str
    itemName: str
    itemIcon: str
    gameId: int

class PopulateItems:
    def __init__(self, appId : int):
        try:
            self.connection = mysql.connector.connect(host=DB_HOST, user=DB_USERNAME, password=DB_PASSWORD, database=DB_DATABASE)
        except Exception as e:
            logging.critical(f"Unable to connect to database: {e}")
            exit(1)
        self.start_index = 0
        self.page_size = 100
        self.appId = appId
    
    def add_item(self, data: Item) -> bool:
        return False
    
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
                if res.status_code != 200:
                    raise Exception(f"Status code was {res.status_code}")
                
                res_json = res.json()
                print(res_json)
                if not res_json['success']:
                    raise Exception(f"Success field was false")
                
                results = res_json.results
                print(results)
            except Exception as e:
                logging.warning(f"An error occured when doing a request: {e}")
                sleep(60)
                continue
            
            if True:
                break

            self.start_index += self.page_size
        
        logging.info("Script finished!")




def main():
    itemPopulator = PopulateItems(730)
    itemPopulator.populate_items()

if __name__ == "__main__":
    main()