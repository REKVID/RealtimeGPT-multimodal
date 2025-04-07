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
from agents.voice import AudioInput
from dotenv import load_dotenv
import asyncio

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

    try:
        while True:
            # Получаем аудиоданные от клиента
            audio_data = await websocket.receive_bytes()

            # Обрабатываем аудио
            try:
                samples = process_audio_data(audio_data)
            except HTTPException as e:
                await websocket.send_text(f"Ошибка: {e.detail}")
                continue
            except Exception as e:
                await websocket.send_text(f"Ошибка обработки аудио: {str(e)}")
                continue

            # Создаем экземпляр аудиовхода
            audio_input = AudioInput(buffer=samples)

            # Создаем голосовой конвейер
            pipeline = create_voice_pipeline()

            # Запускаем обработку и отправляем аудио в реальном времени
            result = await pipeline.run(audio_input)

            # Отправляем статус начала ответа
            await websocket.send_json({"type": "status", "text": "Начало ответа"})

            # Обрабатываем и отправляем каждый фрагмент аудио по мере поступления
            async for event in result.stream():
                if event.type == "voice_stream_event_audio":
                    audio_data = event.data

                    # Отладочная информация о размере фрагмента
                    print(f"Отправка аудиофрагмента размером {len(audio_data)} сэмплов")

                    # Создаем WAV-заголовок для фрагмента
                    header = generate_wav_header(
                        SAMPLE_RATE, SAMPLE_WIDTH * 8, CHANNELS, len(audio_data)
                    )

                    # Отправляем фрагмент аудио
                    await websocket.send_bytes(header + audio_data.tobytes())

                    # Небольшая пауза для обработки клиентом
                    await asyncio.sleep(0.01)

                elif event.type == "voice_stream_event_transcript":
                    # Отправляем транскрипцию текста
                    await websocket.send_json(
                        {"type": "transcript", "text": event.data}
                    )

            # Отправляем статус завершения ответа
            await websocket.send_json({"type": "status", "text": "Ответ завершен"})

    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        if not connection_closed:
            try:
                await websocket.close()
                connection_closed = True
            except RuntimeError:
                # Игнорируем ошибку, если соединение уже закрыто
                pass


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="localhost", port=8001, reload=True)
