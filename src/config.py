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
    regime_detection: Any = field(default_factory=dict)
    adaptive_exits: Any = field(default_factory=dict)
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
        cfg.regime_detection = data.get('regime_detection', {})
        cfg.adaptive_exits = data.get('adaptive_exits', {})

        # Helper to convert nested dicts to objects
        def dict_to_obj(d):
            if isinstance(d, dict):
                obj = type('Obj', (), {})()
                for k, v in d.items():
                    setattr(obj, k, dict_to_obj(v))
                return obj
            return d

        # For convenience, expose nested keys as attributes as well
        cfg.trading = dict_to_obj(cfg.trading)
        cfg.clc_strategy = dict_to_obj(cfg.clc_strategy)
        cfg.risk = dict_to_obj(cfg.risk)
        cfg.scoring = dict_to_obj(cfg.scoring)
        cfg.learning = dict_to_obj(cfg.learning)
        cfg.notifications = dict_to_obj(cfg.notifications)
        cfg.regime_detection = dict_to_obj(cfg.regime_detection)
        cfg.adaptive_exits = dict_to_obj(cfg.adaptive_exits)
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
