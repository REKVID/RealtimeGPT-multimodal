"""
Точка входа в приложение
"""

import os
import logging
import uvicorn
from agents import set_tracing_disabled

from .config import DEBUG_DIR
from .routes import app

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Отключаем трасировку для производительности
set_tracing_disabled(True)

# Создаем директорию для отладки
os.makedirs(DEBUG_DIR, exist_ok=True)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="localhost", port=8000, reload=True)
