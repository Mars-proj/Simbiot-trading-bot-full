import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import aiohttp
import time
import hmac
import hashlib
import pickle
import os.path
from urllib.parse import urlencode
from utils.logging_setup import setup_logging
from dotenv import load_dotenv

logger = setup_logging('mexc_api')

class MEXCAPI:
    def __init__(self, market_state: dict = None):
        self.market_state = market_state
        load_dotenv()
        self.api_key = os.getenv('MEXC_API_KEY')
        self.api_secret = os.getenv('MEXC_API_SECRET')
        if not self.api_key or not self.api_secret:
            logger.error("MEXC API keys not found in .env file")
            raise ValueError("MEXC API keys not found")
        self.base_url = "https://api.mexc.com"
        self.cache_dir = "/root/trading_bot/cache/mexc_klines"
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def _sign_request(self, params: dict) -> dict:
        """Sign the request with API key and secret."""
        timestamp = int(time.time() * 1000)
        params['timestamp'] = timestamp
        params['api_key'] = self.api_key

        query_string = urlencode(sorted(params.items()))
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        params['signature'] = signature
        return params

    async def get_symbols(self) -> list:
        """Fetch all trading symbols from MEXC."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/v3/exchangeInfo") as response:
                    data = await response.json()
                    symbols = [symbol['symbol'] for symbol in data['symbols'] if symbol['status'] == '1']
                    logger.info(f"Fetched {len(symbols)} symbols from MEXC")
                    return symbols
        except Exception as e:
            logger.error(f"Failed to fetch symbols from MEXC: {str(e)}")
            return []

    async def get_klines(self, symbol: str, timeframe: str, limit: int) -> list:
        """Fetch historical klines for a symbol with caching."""
        # Формируем путь к файлу кэша
        cache_file = os.path.join(self.cache_dir, f"{symbol}_{timeframe}_{limit}.pkl")
        
        # Проверяем, есть ли данные в кэше
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    klines = pickle.load(f)
                logger.info(f"Loaded {len(klines)} klines for {symbol} from cache")
                return klines
            except Exception as e:
                logger.warning(f"Failed to load cache for {symbol}: {str(e)}, fetching from API")

        # Если кэша нет или он повреждён, делаем запрос к API
        try:
            params = {
                'symbol': symbol,
                'interval': timeframe,
                'limit': limit
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/v3/klines", params=params) as response:
                    data = await response.json()
                    klines = [
                        {
                            'timestamp': int(kline[0]),
                            'open': float(kline[1]),
                            'high': float(kline[2]),
                            'low': float(kline[3]),
                            'close': float(kline[4]),
                            'volume': float(kline[5])
                        }
                        for kline in data
                    ]
                    logger.info(f"Fetched {len(klines)} klines for {symbol} from MEXC")
                    
                    # Сохраняем данные в кэш
                    try:
                        with open(cache_file, 'wb') as f:
                            pickle.dump(klines, f)
                        logger.info(f"Saved {len(klines)} klines for {symbol} to cache")
                    except Exception as e:
                        logger.warning(f"Failed to save cache for {symbol}: {str(e)}")
                    
                    return klines
        except Exception as e:
            logger.error(f"Failed to fetch klines for {symbol}: {str(e)}")
            return []

    async def place_order(self, symbol: str, side: str, quantity: float) -> dict:
        """Place a market order on MEXC."""
        try:
            params = {
                'symbol': symbol,
                'side': side.upper(),
                'type': 'MARKET',
                'quantity': quantity,
                'recvWindow': 5000
            }
            params = self._sign_request(params)

            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/api/v3/order", params=params) as response:
                    if response.status != 200:
                        logger.error(f"Failed to place order: {await response.text()}")
                        return {}

                    result = await response.json()
                    logger.info(f"Placed {side} order for {symbol}: {result}")
                    return result
        except Exception as e:
            logger.error(f"Failed to place order for {symbol}: {str(e)}")
            return {}
