# helpers/logger.py

import logging
import logging.handlers
import os
import json

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

class ExcludeSpecificMessagesFilter(logging.Filter):
    """
    Custom filter to exclude specific log messages from certain modules.
    """

    def __init__(self, module_name: str, excluded_messages: set):
        super().__init__()
        self.module_name = module_name
        self.excluded_messages = excluded_messages

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Determine if the specified record is to be logged.

        Returns True if the record should be logged, False otherwise.
        """
        if record.module == self.module_name and record.message in self.excluded_messages:
            return False  # Exclude this log record
        return True  # Keep all other records

def get_logger(name: str) -> logging.Logger:
    """
    Configures and returns a logger with the specified name.

    Args:
        name (str): The name of the logger, typically __name__.

    Returns:
        logging.Logger: Configured logger instance.
    """

    # Create a logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Set to DEBUG to allow handlers to filter levels

    # Ensure the logs directory exists
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Create a handler for writing log messages to a file with rotation
    log_file = os.path.join('logs', 'bot.log')
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_file, when='midnight', interval=1, backupCount=30, utc=True
    )
    file_handler.suffix = "%Y-%m-%d"

    # Create a console handler for outputting logs to the console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)  # Set console to INFO to exclude DEBUG

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

    # Set file handler level to DEBUG to include all messages
    file_handler.setLevel(logging.DEBUG)

    # Define excluded messages for specific modules
    excluded_messages = {
        "'Get Token' button clicked.",
        "User reached max verification attempts."
    }

    # Create and add the custom filter to both handlers
    exclude_filter = ExcludeSpecificMessagesFilter(
        module_name="helpers.views",
        excluded_messages=excluded_messages
    )
    file_handler.addFilter(exclude_filter)
    console_handler.addFilter(exclude_filter)

    # Add handlers to the logger if they haven't been added already
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

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
