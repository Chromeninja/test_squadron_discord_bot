# helpers/logger.py

import logging
import logging.handlers
import os
import json
import queue
from config.config_loader import ConfigLoader

class CustomJsonFormatter(logging.Formatter):
    def __init__(self, datefmt=None):
        super().__init__(datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        record_dict = {
            "time": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "module": record.name,
            "funcName": record.funcName,
            "lineno": record.lineno,
            "message": record.getMessage(),
        }
        if hasattr(record, 'user_id'):
            record_dict['user_id'] = record.user_id
        if hasattr(record, 'rsi_handle'):
            record_dict['rsi_handle'] = record.rsi_handle

        return json.dumps(record_dict, ensure_ascii=False)

def setup_logging():
    config = ConfigLoader.load_config()
    logging_config = config.get('logging', {})
    log_level_name = logging_config.get('level', 'INFO').upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    if not os.path.exists('logs'):
        os.makedirs('logs')

    log_queue = queue.Queue(maxsize=1000)
    queue_listener = _build_queue_listener(log_queue, log_level)

    queue_handler = logging.handlers.QueueHandler(log_queue)
    queue_handler.setLevel(log_level)
    root_logger.addHandler(queue_handler)

    queue_listener.start()

    discord_logger = logging.getLogger('discord')
    discord_logger.setLevel(logging.WARNING)

def _build_queue_listener(log_queue: queue.Queue, log_level: int) -> logging.handlers.QueueListener:
    """
    Creates a QueueListener that will dispatch logs from the queue
    to both file and console handlers.
    """
    log_file = os.path.join('logs', 'bot.log')
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_file,
        when='midnight',
        interval=1,
        backupCount=30,
        utc=True
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setLevel(log_level)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    formatter = CustomJsonFormatter(datefmt="%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    return logging.handlers.QueueListener(
        log_queue,
        file_handler,
        console_handler,
        respect_handler_level=True
    )

def get_logger(name: str) -> logging.Logger:
    """
    Convenience method for retrieving a logger
    """
    return logging.getLogger(name)

def set_module_logging_level(module_name: str, level: int):
    """
    Sets the logging level for a specific module.

    Args:
        module_name (str): The name of the module (e.g., 'helpers.rate_limiter').
        level (int): The logging level (e.g., logging.INFO).
    """
    logger = logging.getLogger(module_name)
    logger.setLevel(level)

# Setup logging when the module is imported
setup_logging()
