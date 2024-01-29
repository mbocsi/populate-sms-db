from dataclasses import dataclass
import requests
from time import sleep
import logging
from bs4 import BeautifulSoup
from prisma import Prisma
import asyncio
import os
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, filename="main.log", encoding="utf-8", format="%(asctime)s :: %(levelname)-8s :: %(message)s" )

ITEMS_URL = "https://steamcommunity.com/market/search/render"
HISTORY_URL = "https://steamcommunity.com/market/pricehistory"
ITEM_PAGE_URL = "https://steamcommunity.com/market/listings"

@dataclass
class Item:
    itemNameId: int
    itemHashName: str
    itemName: str
    itemIcon: str
    gameId: int

@dataclass
class Price:
    date: datetime
    price : float
    itemId: str
    volume: int

class PopulateItems:
    def __init__(self, appId : int, start_index : int = 0, page_size : int = 100) -> None:
        try:
            self.db = Prisma()
            logging.info(f"Database object instantiation success!")
        except Exception as e:
            logging.exception(f"Unable to instantiate database object!")
            exit(1)
        self.start_index = start_index
        self.page_size = page_size
        self.appId = appId
    
    async def add_item(self, data: Item) -> bool:
        logging.info(f"Adding the item to database! {data}")
        try:
            await self.db.connect()
            await self.db.item.create(data={**data.__dict__})
            return True
        except Exception as e:
            logging.exception(f"An error occured when inserting into database! -> {data}")
            return False
        finally:
            await self.db.disconnect()
            
    
    async def in_database(self, itemHashName : str) -> bool:
        try:
            await self.db.connect()
            count = await self.db.item.count(where={'itemHashName': itemHashName})
            logging.debug(f"{count=}")
            return bool(count)
        except Exception as e:
            logging.exception("An exception occured when checking for item in database!")
        finally:
            await self.db.disconnect()
    
    async def get_items(self, start : int, count : int) -> list[Item] | bool:
        try:
            await self.db.connect()
            items = await self.db.item.find_many(skip=start, take=count, where={});
            logging.debug(f"{len(items)=}")
            return items
        except Exception as e:
            logging.exception("An exception occured when checking for items in database!")
            return False
        finally:
            await self.db.disconnect()
    
    async def insert_price_history(self, history : list[Price], time_limit : timedelta) -> bool:
        try:
            await self.db.connect()
            to_add = filter(lambda x: datetime.utcnow() - x.date <= time_limit, history)
            await self.db.price.create_many(data=[i.__dict__ for i in to_add])
            logging.debug(f"Added into database: \n{history}")
            return True
        except Exception as e:
            logging.exception("An exception occured when inserting price history into database!")
            return False
        finally:
            await self.db.disconnect()
    
    async def populate_items(self) -> None:
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

                if len(results) == 0: # Results is empty
                    """Exit the loop/program!"""
                    break
                
                for item in results:
                    try:
                        hashName = item["hash_name"]

                        if await self.in_database(hashName):
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
                        script = script[idx+23:]
                        idx = script.find(")")
                        script = script[:idx]
                        script = script.strip()
                        itemNameId = int(script)
                        logging.debug(f"Found ItemNameId: {itemNameId}")

                        marketItem = Item(itemNameId, hashName, item['name'], item['asset_description']['icon_url'], item['asset_description']['appid'])
                        if not await self.add_item(marketItem):
                            logging.warning("Failed to insert item into database!")
                            """Do nothing else for now, just skip"""

                        logging.info("Sleeping for 10 seconds!")
                        sleep(10)
                        
                    except Exception:
                        logging.exception(f"An error occured when doing an item market request")
                        logging.info("Sleeping for 60 seconds!")
                        sleep(60)

            except Exception:
                logging.exception(f"An error occured when doing an item batch request")
                logging.info("Sleeping for 60 seconds!")
                sleep(60)
                continue

            self.start_index += self.page_size
        
        logging.info("Script finished!")
    
    async def populate_history(self, steamLoginSecure : str, time_limit : timedelta) -> None:
        start = 0
        count = 100
        while(1):
            logging.info(f"Getting items {start} to {start+count} from database!")
            items = await self.get_items(start, count)
            if not items:
                logging.warning(f"Error when getting items from db! Sleeping 5 seconds!")
                sleep(5)
                continue
            if len(items) == 0:
                break
            for item in items:
                try:
                    logging.info(f"Processing {item.itemHashName}")
                    res = requests.get(HISTORY_URL, params={
                        "currency": 1,
                        "appid": self.appId,
                        "market_hash_name": item.itemHashName
                    }, cookies={"steamLoginSecure": steamLoginSecure})
                    logging.debug(f"Requested {res.request}")
                    if res.status_code != 200:
                        raise Exception(f"Status code for {HISTORY_URL} was {res.status_code}")
                    
                    res_json = res.json()
                    logging.debug(f"Response JSON: {res_json}")
                    if not res_json['success']:
                        raise Exception(f"Success field was false")
                    
                    history = res_json["prices"]

                    prices = [Price(datetime.strptime(price[0], "%b %d %Y %H: +%M"), price[1], item.itemNameId, int(price[2])) for price in history]

                    if(not await self.insert_price_history(prices, time_limit)):
                        logging.warning("Failed to insert price history into database! Sleeping 3 seconds!")
                    else:
                        logging.info(f"Added price history for {item.itemHashName}! Sleeping 3 seconds!")
                    sleep(3)
                except Exception:
                    logging.exception(f"An error occured when doing an item history request")
                    logging.info("Sleeping for 60 seconds!")
                    sleep(60)
                    continue
            
            start+=count

async def delete(item):
    await item.db.connect()
    await item.db.price.delete_many(where={})
    await item.db.disconnect()

def main() -> None:
    itemPopulator = PopulateItems(730)
    # asyncio.run(delete(itemPopulator))
    # asyncio.run(itemPopulator.populate_items())
    asyncio.run(itemPopulator.populate_history(os.getenv("STEAM_LOGIN_SECURE"), timedelta(days=365)))

if __name__ == "__main__":
    main()