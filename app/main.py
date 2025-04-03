import os
import numpy as np
from fastapi import FastAPI, UploadFile, File, WebSocket
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from pydub import AudioSegment
import io
from agents.voice import AudioInput
from dotenv import load_dotenv

# Изменяем импорты
from agents import set_tracing_disabled
from .voice_agents import create_voice_pipeline


# Загружаем переменные окружения из .env файла
load_dotenv()

# Проверяем наличие API ключа
if not os.getenv("OPENAI_API_KEY"):
    print("API ")


# Отключаем трассировку для повышения производительности
set_tracing_disabled(True)

app = FastAPI()

# Монтируем статические файлы
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("static/index.html", "r") as f:
        return f.read()


@app.post("/process-audio/")
async def process_audio(audio: UploadFile = File(...)):
    # Читаем аудиофайл
    audio_data = await audio.read()

    # Конвертируем аудио в нужный формат
    audio_segment = AudioSegment.from_file(io.BytesIO(audio_data))
    audio_segment = audio_segment.set_frame_rate(24000).set_channels(1)

    # Преобразуем в numpy массив
    samples = np.array(audio_segment.get_array_of_samples(), dtype=np.int16)

    # Создаем экземпляр аудиовхода
    audio_input = AudioInput(buffer=samples)

    # Создаем голосовой конвейер
    pipeline = create_voice_pipeline()

    # Запускаем обработку
    result = await pipeline.run(audio_input)

    # Функция для стриминга аудио
    async def stream_response():
        async for event in result.stream():
            if event.type == "voice_stream_event_audio":
                # Преобразуем numpy array в байты
                yield event.data.tobytes()

    # Возвращаем стримингответ
    return StreamingResponse(
        stream_response(),
        media_type="audio/pcm",
        headers={"Content-Disposition": "attachment; filename=response.pcm"},
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            # Получаем аудиоданные от клиента
            audio_data = await websocket.receive_bytes()

            # Конвертируем в нужный формат
            audio_segment = AudioSegment.from_file(io.BytesIO(audio_data))
            audio_segment = audio_segment.set_frame_rate(24000).set_channels(1)

            # Преобразуем в numpy массив
            samples = np.array(audio_segment.get_array_of_samples(), dtype=np.int16)

            # Создаем экземпляр аудиовхода
            audio_input = AudioInput(buffer=samples)

            # Создаем голосовой конвейер
            pipeline = create_voice_pipeline()

            # Запускаем обработку
            result = await pipeline.run(audio_input)

            # Отправляем ответ клиенту
            async for event in result.stream():
                if event.type == "voice_stream_event_audio":
                    await websocket.send_bytes(event.data.tobytes())

    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="localhost", port=8000, reload=True)
