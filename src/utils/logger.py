"""
Logging utility
"""
import logging
import colorlog
from pathlib import Path

def setup_logger(name: str) -> logging.Logger:
    Path('logs').mkdir(exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    cf = colorlog.ColoredFormatter(
        '%(log_color)s[%(levelname)s]%(reset)s %(message)s',
        log_colors={'DEBUG': 'cyan', 'INFO': 'green', 'WARNING': 'yellow', 'ERROR': 'red'}
    )
    ch.setFormatter(cf)
    logger.addHandler(ch)

    fh = logging.FileHandler('logs/bot.log')
    fh.setLevel(logging.INFO)
    ff = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    fh.setFormatter(ff)
    logger.addHandler(fh)
    return logger

