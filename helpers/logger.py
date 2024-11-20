# helpers/logger.py

import logging
import logging.handlers
import os
import json
from config.config_loader import ConfigLoader

class CustomJsonFormatter(logging.Formatter):
    """
    Custom formatter to output logs in JSON format.
    """
    def __init__(self, fmt: dict, datefmt: str = None):
        super().__init__(datefmt=datefmt)
        self.fmt = fmt

    def format(self, record):
        # Add 'asctime' if it's part of the format
        if '%(asctime)s' in self.fmt.values():
            record.asctime = self.formatTime(record, self.datefmt)

        # Ensure 'message' is set
        record.message = record.getMessage()

        # Create the record dictionary with formatted values
        record_dict = {}
        for key, value in self.fmt.items():
            if '%' in value:
                try:
                    record_dict[key] = value % record.__dict__
                except KeyError as e:
                    record_dict[key] = f"Missing key: {e}"
            else:
                record_dict[key] = value

        # Add user IDs if available in the record
        if hasattr(record, 'user_id'):
            record_dict['user_id'] = record.user_id
        if hasattr(record, 'rsi_handle'):
            record_dict['rsi_handle'] = record.rsi_handle

        return json.dumps(record_dict)

def setup_logging():
    """
    Sets up the root logger with file and console handlers.
    """
    config = ConfigLoader.load_config()
    logging_config = config.get('logging', {})
    log_level_str = logging_config.get('level', 'INFO').upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all messages at the root logger

    # Remove all handlers associated with the root logger
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Ensure the logs directory exists
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Create a handler for writing log messages to a file with rotation
    log_file = os.path.join('logs', 'bot.log')
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_file, when='midnight', interval=1, backupCount=30, utc=True
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setLevel(log_level)  # Set file handler level based on config

    # Create a console handler for outputting logs to the console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)  # Set console handler level based on config

    # Define the log format
    log_format = {
        "time": "%(asctime)s",
        "level": "%(levelname)s",
        "module": "%(name)s",
        "message": "%(message)s"
    }
    formatter = CustomJsonFormatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")

    # Set formatter for both handlers
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add handlers to the root logger
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Set the logging level for the 'discord' logger to WARNING to suppress debug logs
    discord_logger = logging.getLogger('discord')
    discord_logger.setLevel(logging.WARNING)
    
def get_logger(name: str) -> logging.Logger:
    """
    Retrieves a logger with the given name. Assumes root logger is already configured.

    Args:
        name (str): The name of the logger.

    Returns:
        logging.Logger: The configured logger.
    """
    logger = logging.getLogger(name)
    return logger

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
