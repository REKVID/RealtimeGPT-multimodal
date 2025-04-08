import os
import numpy as np
from fastapi import FastAPI, UploadFile, File, WebSocket, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
import io
import wave
import struct
import time
import logging
from agents.voice import AudioInput
from dotenv import load_dotenv

# Изменяем импорты
from agents import set_tracing_disabled
from app.voice_agents import create_voice_pipeline

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("voice_app")

# Загружаем переменные окружения из .env файла
load_dotenv()

# Проверяем наличие API ключа
if not os.getenv("OPENAI_API_KEY"):
    print("API key miss")


# Отключаем трассировку для повышения производительности
set_tracing_disabled(True)

app = FastAPI()

# Конфигурация аудио
SAMPLE_RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16 бит
MIN_AUDIO_LENGTH = SAMPLE_RATE * 0.5  # Минимум 0.5 секунды

# Словарь для хранения постоянных соединений
active_connections = {}

# Создаем папку для отладочных файлов
os.makedirs("debug", exist_ok=True)

# Монтируем статические файлы
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


def generate_wav_header(sample_rate, bits_per_sample, channels, n_samples):
    """Генерирует WAV-заголовок для аудио данных"""
    datasize = n_samples * channels * bits_per_sample // 8
    header = bytes("RIFF", "ascii")
    header += struct.pack("<L", 36 + datasize)
    header += bytes("WAVE", "ascii")
    header += bytes("fmt ", "ascii")
    header += struct.pack("<L", 16)
    header += struct.pack("<H", 1)  # PCM формат
    header += struct.pack("<H", channels)
    header += struct.pack("<L", sample_rate)
    header += struct.pack(
        "<L", sample_rate * channels * bits_per_sample // 8
    )  # байт/сек
    header += struct.pack("<H", channels * bits_per_sample // 8)  # блок выравнивания
    header += struct.pack("<H", bits_per_sample)
    header += bytes("data", "ascii")
    header += struct.pack("<L", datasize)
    return header


def process_audio_data(audio_data, connection_id=None, session=None):
    """Обрабатывает входные аудиоданные и возвращает нормализованные сэмплы"""
    debug_prefix = (
        f"debug/audio_{connection_id}_{session}"
        if connection_id and session
        else "debug/audio"
    )
    timestamp = int(time.time())

    try:
        # Сохраняем исходный формат аудио для диагностики
        with open(f"{debug_prefix}_raw_{timestamp}.bin", "wb") as f:
            f.write(audio_data)

        # Определяем тип файла по первым байтам
        file_type = ""
        if len(audio_data) > 10:
            if audio_data.startswith(b"RIFF"):
                file_type = "wav"
            elif audio_data.startswith(b"\xff\xfb") or audio_data.startswith(b"ID3"):
                file_type = "mp3"
            elif audio_data.startswith(b"OggS"):
                file_type = "ogg"
            elif audio_data.startswith(b"fLaC"):
                file_type = "flac"

        logger.info(
            f"Аудио формат определен как: {file_type or 'неизвестный'}, размер: {len(audio_data)} байт"
        )

        # Для аудиоданных без явного формата, добавляем WAV заголовок
        if not file_type and len(audio_data) > 44:
            # Предполагаем, что это сырые PCM данные
            logger.info("Принимаем данные как сырые PCM, добавляем WAV заголовок")

            # Проверяем, что данные могут быть PCM Int16
            try:
                # Преобразуем в numpy массив для проверки

                # Создаем временный WAV-файл
                with wave.open(
                    f"{debug_prefix}_with_header_{timestamp}.wav", "wb"
                ) as wav_file:
                    wav_file.setnchannels(CHANNELS)
                    wav_file.setsampwidth(SAMPLE_WIDTH)
                    wav_file.setframerate(SAMPLE_RATE)
                    wav_file.writeframes(audio_data)

                # Читаем как AudioSegment
                audio_segment = AudioSegment.from_file(
                    f"{debug_prefix}_with_header_{timestamp}.wav", format="wav"
                )
            except Exception as e:
                logger.error(f"Не удалось обработать как PCM данные: {e}")
                # Продолжаем, пытаясь обработать как обычный файл

        # Конвертируем аудио в нужный формат
        audio_segment = AudioSegment.from_file(io.BytesIO(audio_data))
        audio_segment = (
            audio_segment.set_frame_rate(SAMPLE_RATE)
            .set_channels(CHANNELS)
            .set_sample_width(SAMPLE_WIDTH)
        )

        # Нормализуем уровень громкости
        audio_segment = audio_segment.normalize()

        # Сохраняем конвертированное аудио для диагностики
        audio_segment.export(f"{debug_prefix}_converted_{timestamp}.wav", format="wav")

    except CouldntDecodeError:
        logger.error(
            f"Невозможно декодировать аудио. Размер данных: {len(audio_data)} байт"
        )
        raise HTTPException(
            400,
            "Невозможно декодировать аудио. Поддерживаются форматы WAV, MP3, OGG и другие.",
        )
    except Exception as e:
        logger.error(
            f"Ошибка обработки аудио: {str(e)}, размер данных: {len(audio_data)} байт"
        )
        raise HTTPException(500, f"Ошибка обработки аудио: {str(e)}")

    # Преобразуем в numpy массив
    samples = np.array(audio_segment.get_array_of_samples(), dtype=np.int16)

    # Логируем информацию о сэмплах
    logger.info(
        f"Получено {len(samples)} сэмплов аудио, длительность: {len(samples) / SAMPLE_RATE:.2f} сек"
    )

    # Проверяем минимальную длину аудио
    if len(samples) < MIN_AUDIO_LENGTH:
        logger.warning(
            f"Аудио слишком короткое: {len(samples)} сэмплов < {MIN_AUDIO_LENGTH} минимум"
        )
        raise HTTPException(
            400,
            f"Аудио слишком короткое, минимум 0.5 секунды ({MIN_AUDIO_LENGTH} сэмплов)",
        )

    return samples


@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("static/index.html", "r") as f:
        return f.read()



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connection_closed = False

    # Создаем уникальный идентификатор для соединения
    connection_id = id(websocket)
    logger.info(f"Новое WebSocket соединение: {connection_id}")

    # Создаем голосовой конвейер только один раз для соединения с явным указанием языка
    if connection_id not in active_connections:
        active_connections[connection_id] = {
            "pipeline": create_voice_pipeline(language="ru"),
            "session_count": 0,
        }

    try:
        while True:
            # Получаем аудиоданные от клиента
            audio_data = await websocket.receive_bytes()

            # Увеличиваем счетчик сессий
            active_connections[connection_id]["session_count"] += 1
            session_count = active_connections[connection_id]["session_count"]

            logger.info(
                f"Получены аудиоданные для {connection_id}, сессия {session_count}, размер: {len(audio_data)} байт"
            )

            # Обрабатываем аудио
            try:
                samples = process_audio_data(audio_data, connection_id, session_count)
            except HTTPException as e:
                logger.error(f"HTTP ошибка при обработке аудио: {e.detail}")
                await websocket.send_text(f"Ошибка: {e.detail}")
                continue
            except Exception as e:
                logger.error(f"Неожиданная ошибка при обработке аудио: {str(e)}")
                await websocket.send_text(f"Ошибка обработки аудио: {str(e)}")
                continue

            # Создаем экземпляр аудиовхода
            audio_input = AudioInput(buffer=samples)

            # Используем существующий конвейер для этого соединения
            pipeline = active_connections[connection_id]["pipeline"]

            # Запускаем обработку
            logger.info(f"Запуск обработки для {connection_id}, сессия {session_count}")
            result = await pipeline.run(audio_input)

            # Получаем все аудиоданные и собираем их в один массив
            all_audio = []
            async for event in result.stream():
                if event.type == "voice_stream_event_audio":
                    all_audio.append(event.data)

            # Если есть данные, отправляем их как один WAV-файл
            if all_audio:
                # Объединяем все фрагменты
                combined_audio = np.concatenate(all_audio)

                logger.info(
                    f"Отправка ответа для {connection_id}, сессия {session_count}, размер: {len(combined_audio)} сэмплов"
                )

                # Создаем WAV-заголовок для всего аудио
                header = generate_wav_header(
                    SAMPLE_RATE, SAMPLE_WIDTH * 8, CHANNELS, len(combined_audio)
                )

                # Отправляем полный WAV-файл
                await websocket.send_bytes(header + combined_audio.tobytes())
            else:
                logger.warning(
                    f"Нет аудио данных для ответа, соединение {connection_id}, сессия {session_count}"
                )

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if connection_id in active_connections:
            logger.info(f"Закрытие соединения {connection_id}")
            del active_connections[connection_id]
        if not connection_closed:
            try:
                await websocket.close()
                connection_closed = True
            except RuntimeError:
                # Игнорируем ошибку, если соединение уже закрыто
                pass


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="localhost", port=8001, reload=True)
