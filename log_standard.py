import logging
import os
import datetime
import sys

class CustomLogger:
    # Define logging level constants
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL
    def __init__(self, file_handler_level=INFO, terminal_handler_level=INFO, log_directory=None):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

        if log_directory is None:
            log_directory = os.path.join(os.path.dirname(__file__), '.', 'logs')
        self.setup_log_directory(log_directory)

        self.setup_handlers(file_handler_level, terminal_handler_level)
    def setup_log_directory(self, log_directory):
        if not os.path.exists(log_directory):
            os.makedirs(log_directory)
        self.log_path = os.path.join(log_directory, f'log_{datetime.datetime.today().strftime("%Y%m%d")}.log')
    def setup_handlers(self, file_handler_level, terminal_handler_level):
        formatter = logging.Formatter('%(asctime)s | %(module)s | %(funcName)s | %(levelname)s | %(filename)s | %(lineno)d | %(message)s')

        file_handler = logging.FileHandler(self.log_path)
        file_handler.setLevel(file_handler_level)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        terminal_handler = logging.StreamHandler(sys.stdout)
        terminal_handler.setLevel(terminal_handler_level)
        terminal_handler.setFormatter(formatter)
        self.logger.addHandler(terminal_handler)
