import os
import logging
import asyncio
import numpy as np
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from agents.voice import AudioInput

from .config import STATIC_DIR 
from .audio import process_audio_data, generate_wav_header
from .voice_agents import create_voice_pipeline

# Настройка логирования
logger = logging.getLogger("voice_app")


app = FastAPI()

# Словарь для хранения постоянных соединений
active_connections = {}

# Монтируем статическ
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Возвращает главную страницу"""
    with open(f"{STATIC_DIR}/index.html", "r") as f:
        return f.read()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Обработчик WebSocket соединений для аудио взаимодействия.

    Этот эндпоинт обрабатывает входящие аудио потоки, отправляет их
    на обработку голосовому агенту и возвращает сгенерированные
    аудио ответы.

    Args:
        websocket (WebSocket): WebSocket соединение.

    Raises:
        HTTPException: При ошибках обработки аудио.

    Example:
        >>> async with websocket.connect("ws://localhost:8000/ws") as ws:
        ...     await ws.send_bytes(audio_data)
        ...     response = await ws.receive_bytes()
    """
    await websocket.accept()
    connection_closed = False

    # Создаем уникальный идентификатор для соединения (ХУЙНЯ НО ПОКА ЧТО НЕ ТРОГАТЬ)
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
                samples = process_audio_data(audio_data)
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

            max_retries = 3
            retry_delay = 1.0

            for retry in range(max_retries):
                try:
                    result = await pipeline.run(audio_input)

                    # Получаем все аудиоданные и собираем их в один массив
                    all_audio = []
                    async for event in result.stream():
                        if event.type == "voice_stream_event_audio":
                            all_audio.append(event.data)

                    # Если есть данные, отправляем их как один WAV-файл
                    if all_audio:
                        try:
                            # Объединяем все фрагменты
                            combined_audio = np.concatenate(all_audio)

                            # Создаем WAV заголовок
                            wav_header = generate_wav_header(len(combined_audio))

                            # Отправляем аудио клиенту
                            await websocket.send_bytes(
                                wav_header + combined_audio.tobytes()
                            )
                            logger.info(
                                f"Аудио успешно отправлено клиенту, размер: {len(combined_audio)} сэмплов"
                            )
                            break  # Выходим из цикла повторных попыток при успехе

                        except Exception as e:
                            logger.error(
                                f"Ошибка при отправке аудио (попытка {retry + 1}/{max_retries}): {str(e)}"
                            )
                            if retry < max_retries - 1:
                                await asyncio.sleep(retry_delay)
                                retry_delay *= 2  # Увеличиваем задержку между попытками
                            else:
                                # Если все попытки исчерпаны, отправляем текстовое сообщение
                                await websocket.send_text(
                                    "Ошибка при отправке аудио-ответа. Попробуйте еще раз."
                                )
                                logger.error(
                                    f"Не удалось отправить аудио после {max_retries} попыток"
                                )

                    break  # Выходим из цикла повторных попыток при успехе

                except Exception as e:
                    logger.error(
                        f"Ошибка при обработке запроса (попытка {retry + 1}/{max_retries}): {str(e)}"
                    )
                    if retry < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        await websocket.send_text(
                            f"Ошибка при обработке запроса: {str(e)}"
                        )
                        logger.error(
                            f"Не удалось обработать запрос после {max_retries} попыток"
                        )

    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        if not connection_closed:
            await websocket.close()
    finally:
        # Очищаем ресурсы при закрытии соединения
        logger.info(f"Закрытие соединения {connection_id}")
        if connection_id in active_connections:
            del active_connections[connection_id]
