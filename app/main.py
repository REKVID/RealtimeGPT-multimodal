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
import json
import asyncio
from agents.voice import AudioInput, StreamedAudioInput
from dotenv import load_dotenv

# Изменяем импорты
from agents import set_tracing_disabled
from app.voice_agents import create_voice_pipeline


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
CHUNK_SIZE = 4096  # Размер буфера для потоковой передачи

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


def process_audio_data(audio_data):
    """Обрабатывает входные аудиоданные и возвращает нормализованные сэмплы"""
    try:
        # Конвертируем аудио в нужный формат
        audio_segment = AudioSegment.from_file(io.BytesIO(audio_data))
        audio_segment = (
            audio_segment.set_frame_rate(SAMPLE_RATE)
            .set_channels(CHANNELS)
            .set_sample_width(SAMPLE_WIDTH)
        )
    except CouldntDecodeError:
        raise HTTPException(
            400,
            "Невозможно декодировать аудио. Поддерживаются форматы WAV, MP3, OGG и другие.",
        )

    # Преобразуем в numpy массив
    samples = np.array(audio_segment.get_array_of_samples(), dtype=np.int16)

    # Проверяем минимальную длину аудио
    if len(samples) < MIN_AUDIO_LENGTH:
        raise HTTPException(400, "Аудио слишком короткое, минимум 0.5 секунды")

    return samples


@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("static/index.html", "r") as f:
        return f.read()


@app.post("/process-audio/")
async def process_audio(audio: UploadFile = File(...)):
    # Читаем аудиофайл
    audio_data = await audio.read()

    # Обрабатываем аудио
    try:
        samples = process_audio_data(audio_data)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(500, f"Ошибка обработки аудио: {str(e)}")

    # Создаем экземпляр аудиовхода
    audio_input = AudioInput(buffer=samples)

    # Создаем голосовой конвейер
    pipeline = create_voice_pipeline()

    # Запускаем обработку
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

        # Создаем WAV-файл в памяти
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(combined_audio.tobytes())

        # Возвращаемся в начало буфера
        wav_io.seek(0)

        # Возвращаем WAV-файл
        return StreamingResponse(
            wav_io,
            media_type="audio/wav",
            headers={"Content-Disposition": "attachment; filename=response.wav"},
        )

    # Если нет данных, возвращаем пустой ответ
    return StreamingResponse(
        io.BytesIO(b""),
        media_type="audio/wav",
        headers={"Content-Disposition": "attachment; filename=response.wav"},
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connection_closed = False

    # Создаем голосовой конвейер
    pipeline = create_voice_pipeline()

    # Создаем потоковый аудиовход
    streamed_input = StreamedAudioInput()

    # Запускаем трансляцию в отдельном таске
    streaming_task = None

    try:
        while True:
            # Принимаем команды или данные от клиента
            message = await websocket.receive()

            # Если это бинарные данные (аудио)
            if "bytes" in message:
                audio_data = message["bytes"]

                try:
                    # Обрабатываем аудио
                    samples = process_audio_data(audio_data)

                    # Отправляем клиенту статус о начале обработки
                    await websocket.send_json({"status": "processing"})

                    # Если есть активная задача, отменяем её перед новым запросом
                    if streaming_task and not streaming_task.done():
                        streaming_task.cancel()
                        try:
                            await streaming_task
                        except asyncio.CancelledError:
                            pass

                    # Создаем новый потоковый ввод для каждого запроса
                    streamed_input = StreamedAudioInput()

                    # Добавляем аудио в потоковый ввод
                    await streamed_input.add_audio(samples)

                    # Запускаем конвейер
                    result = await pipeline.run(streamed_input)

                    # Запускаем асинхронную задачу для трансляции ответа
                    streaming_task = asyncio.create_task(
                        stream_result_to_client(websocket, result)
                    )

                except HTTPException as e:
                    await websocket.send_json({"error": e.detail})
                except Exception as e:
                    await websocket.send_json({"error": str(e)})

            # Если это текстовые команды
            elif "text" in message:
                command = json.loads(message["text"])

                # Обработка команды остановки
                if command.get("action") == "stop":
                    if streaming_task and not streaming_task.done():
                        streaming_task.cancel()
                    await websocket.send_json({"status": "stopped"})

    except asyncio.CancelledError:
        print("WebSocket connection cancelled")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        # Отменяем задачу трансляции, если она еще активна
        if streaming_task and not streaming_task.done():
            streaming_task.cancel()

        if not connection_closed:
            try:
                await websocket.close()
                connection_closed = True
            except RuntimeError:
                # Игнорируем ошибку, если соединение уже закрыто
                pass


async def stream_result_to_client(websocket, result):
    """Потоковая передача результатов от VoicePipeline клиенту"""
    header_sent = False
    buffer_size = 0
    buffer = []

    # Вспомогательная функция для безопасной отправки данных
    async def safe_send(data, is_bytes=False):
        try:
            if is_bytes:
                await websocket.send_bytes(data)
            else:
                await websocket.send_json(data)
            return True
        except RuntimeError as e:
            # Если соединение закрыто, просто логируем и продолжаем
            if "close message has been sent" in str(e):
                print("WebSocket уже закрыт, отправка отменена")
                return False
            raise
        except Exception as e:
            print(f"Ошибка отправки через WebSocket: {e}")
            return False

    try:
        async for event in result.stream():
            # Обработка аудиоданных
            if event.type == "voice_stream_event_audio":
                # Накапливаем данные в буфере
                buffer.append(event.data)
                buffer_size += len(event.data)

                # Когда достигаем достаточного размера буфера, отправляем данные
                if buffer_size >= CHUNK_SIZE or len(buffer) >= 5:
                    # Объединяем буфер
                    combined_data = np.concatenate(buffer)

                    # Если первый фрагмент, отправляем с WAV-заголовком
                    if not header_sent:
                        header = generate_wav_header(
                            SAMPLE_RATE, SAMPLE_WIDTH * 8, CHANNELS, len(combined_data)
                        )
                        if not await safe_send(
                            header + combined_data.tobytes(), is_bytes=True
                        ):
                            return
                        header_sent = True
                    else:
                        if not await safe_send(combined_data.tobytes(), is_bytes=True):
                            return

                    # Очищаем буфер
                    buffer = []
                    buffer_size = 0

            # Обработка событий жизненного цикла
            elif event.type == "voice_stream_event_lifecycle":
                # Отправляем информацию о событии жизненного цикла
                if not await safe_send({"lifecycle": str(event)}):
                    return

                ########################################################################################
                # Выводим транскрибированный текст, если доступен
                if event.type == "voice_stream_event_lifecycle":
                    print(f"Тип события: {event.type}")
                    print(f"Событие: {event}")

                    # Безопасный вывод структуры события
                    try:
                        print(f"Структура события: {dir(event)}")

                        if hasattr(event, "data"):
                            print(f"Событие имеет данные: {event.data}")
                            print(f"Структура data: {dir(event.data)}")

                            # Проверяем возможные поля, содержащие текст
                            if hasattr(event.data, "text") and event.data.text:
                                print(f"Текст: {event.data.text}")
                            elif (
                                hasattr(event.data, "transcript")
                                and event.data.transcript
                            ):
                                print(f"Транскрипт: {event.data.transcript}")
                            elif hasattr(event.data, "message") and event.data.message:
                                print(f"Сообщение: {event.data.message}")
                    except Exception as e:
                        print(f"Ошибка при обработке события: {e}")
                ########################################################################################

            # Обработка ошибок
            elif event.type == "voice_stream_event_error":
                if not await safe_send({"error": str(event.error)}):
                    return

        # Отправляем оставшиеся данные из буфера
        if buffer:
            combined_data = np.concatenate(buffer)
            if not header_sent:
                header = generate_wav_header(
                    SAMPLE_RATE, SAMPLE_WIDTH * 8, CHANNELS, len(combined_data)
                )
                if not await safe_send(header + combined_data.tobytes(), is_bytes=True):
                    return
            else:
                if not await safe_send(combined_data.tobytes(), is_bytes=True):
                    return

        # Отправляем сигнал о завершении
        await safe_send({"status": "completed"})

    except asyncio.CancelledError:
        # Отправляем сигнал об отмене
        await safe_send({"status": "cancelled"})
        raise
    except Exception as e:
        # Отправляем информацию об ошибке
        print(f"Ошибка в потоковой передаче: {e}")
        await safe_send({"error": str(e)})


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="localhost", port=8002, reload=True)
