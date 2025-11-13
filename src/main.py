# Minimal main placeholder
import asyncio
from core.bot import ScalperBot
from src.utils.logger import setup_logger
from config import Config
from dotenv import load_dotenv
load_dotenv()
logger = setup_logger(__name__)
async def main():
    cfg = Config.from_yaml('config/bot_config.yaml')
    bot = ScalperBot(cfg)
    await bot.initialize()
    await bot.run()
if __name__ == "__main__":
    asyncio.run(main())
