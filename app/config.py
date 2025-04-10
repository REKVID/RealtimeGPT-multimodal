"""
Конфигурационные параметры приложения
"""

import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Проверка API ключа
if not os.getenv("OPENAI_API_KEY"):
    print("API key miss")

# Конфигурация аудио
SAMPLE_RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16 бит
MIN_AUDIO_LENGTH = SAMPLE_RATE * 0.5  # Минимум 0.5 секунды

# Пути к директориям
STATIC_DIR = "static"
