import yaml, os
from dataclasses import dataclass, field
from typing import Any
@dataclass
class Config:
    trading: Any = field(default_factory=dict)
    clc_strategy: Any = field(default_factory=dict)
    risk: Any = field(default_factory=dict)
    scoring: Any = field(default_factory=dict)
    learning: Any = field(default_factory=dict)
    notifications: Any = field(default_factory=dict)
    api_key: str = os.getenv("BINANCE_API_KEY","")
    api_secret: str = os.getenv("BINANCE_API_SECRET","")
    discord_webhook_url: str = os.getenv("DISCORD_WEBHOOK_URL","")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN","")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID","")
    @classmethod
    def from_yaml(cls, filepath: str):
        with open(filepath,'r') as f:
            data = yaml.safe_load(f)
        cfg = cls()
        cfg.trading = data.get('trading', {})
        cfg.clc_strategy = data.get('clc_strategy', {})
        cfg.risk = data.get('risk', {})
        cfg.scoring = data.get('scoring', {})
        cfg.learning = data.get('learning', {})
        cfg.notifications = data.get('notifications', {})
        # For convenience, expose nested keys as attributes as well
        class B: pass
        cfg.trading = type('T', (), cfg.trading)()
        cfg.clc_strategy = type('C', (), cfg.clc_strategy)()
        cfg.risk = type('R', (), cfg.risk)()
        cfg.scoring = type('S', (), cfg.scoring)()
        cfg.learning = type('L', (), cfg.learning)()
        cfg.notifications = type('N', (), cfg.notifications)()
        return cfg

def load_config(config_path: str = 'config/bot_config.yaml') -> Config:
    """
    Helper function to load configuration from YAML file.

    Args:
        config_path: Path to configuration file

    Returns:
        Config object with loaded settings
    """
    return Config.from_yaml(config_path)
