import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = "logs"
LOG_LEVEL = logging.INFO
LOG_FORMATTER = logging.Formatter(
    "%(asctime)s [%(levelname)s] [%(name)s] [%(module)s:%(lineno)d] - %(message)s"
)

# 로그 경로 설정
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

console_handler = logging.StreamHandler()
console_handler.setFormatter(LOG_FORMATTER)
console_handler.setLevel(LOG_LEVEL)

file_handler = RotatingFileHandler(
    filename=f"{LOG_DIR}/app.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=15,
    encoding="utf-8"
)
file_handler.setFormatter(LOG_FORMATTER)

root_logger = logging.getLogger()
root_logger.setLevel(LOG_LEVEL)
if not root_logger.handlers:
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

# 불필요 로거 레벨 설정
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

def get_logger(name: str) -> logging.Logger:       
    return logging.getLogger(name)

