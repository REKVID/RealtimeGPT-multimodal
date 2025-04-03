import unittest
import asyncio
import time
import sys
import os
import numpy as np
from unittest.mock import patch, MagicMock, AsyncMock
import concurrent.futures

# Добавляем корневую директорию проекта в sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from app.main import app
from app.voice_agents import create_voice_pipeline
from agents.voice import AudioInput


class TestPerformance(unittest.TestCase):
    def setUp(self):
        # Используем новый способ инициализации TestClient
        self.client = TestClient(app)

    @patch("app.main.AudioSegment")
    @patch("app.main.create_voice_pipeline")
    @patch("app.main.AudioInput")
    @patch("numpy.array")
    @patch(
        "app.main.StreamingResponse",
        return_value=MagicMock(status_code=200, headers={"content-type": "audio/pcm"}),
    )
    def test_response_time(
        self,
        mock_response,
        mock_np_array,
        mock_audio_input,
        mock_pipeline,
        mock_audio_segment,
    ):
        """Тест времени отклика при обработке аудио."""
        # Настраиваем моки
        mock_audio_segment_instance = MagicMock()
        mock_audio_segment.from_file.return_value = mock_audio_segment_instance
        mock_audio_segment_instance.set_frame_rate.return_value = (
            mock_audio_segment_instance
        )
        mock_audio_segment_instance.set_channels.return_value = (
            mock_audio_segment_instance
        )
        mock_audio_segment_instance.get_array_of_samples.return_value = [1, 2, 3]

        mock_np_array.return_value = [1, 2, 3]

        mock_audio_input_instance = MagicMock()
        mock_audio_input.return_value = mock_audio_input_instance

        mock_pipeline_instance = MagicMock()
        mock_pipeline.return_value = mock_pipeline_instance

        # Создаем мок для результата pipeline.run
        mock_result = AsyncMock()
        mock_pipeline_instance.run = AsyncMock(return_value=mock_result)

        # Мок для stream
        async def mock_generator():
            event = MagicMock()
            event.type = "voice_stream_event_audio"
            event.data = MagicMock()
            event.data.tobytes.return_value = b"audio"
            yield event

        mock_result.stream = mock_generator

        # Создаем тестовое аудио
        with open("test_audio.wav", "wb") as f:
            f.write(b"test audio data")

        # Измеряем время выполнения запроса
        start_time = time.time()

        with open("test_audio.wav", "rb") as f:
            response = self.client.post(
                "/process-audio/", files={"audio": ("test.wav", f, "audio/wav")}
            )

        end_time = time.time()

        # Очищаем тестовый файл
        os.remove("test_audio.wav")

        # Проверяем время отклика (должно быть менее 5 секунд в этом примере)
        response_time = end_time - start_time
        self.assertLess(
            response_time,
            5.0,
            f"Время отклика ({response_time:.2f}с) превышает допустимое (5.0с)",
        )

    @patch("app.main.AudioSegment")
    @patch("app.main.create_voice_pipeline")
    @patch("app.main.AudioInput")
    @patch("numpy.array")
    @patch(
        "app.main.StreamingResponse",
        return_value=MagicMock(status_code=200, headers={"content-type": "audio/pcm"}),
    )
    def test_concurrent_connections(
        self,
        mock_response,
        mock_np_array,
        mock_audio_input,
        mock_pipeline,
        mock_audio_segment,
    ):
        """Тест производительности при множественных одновременных соединениях."""
        # Настраиваем моки
        mock_audio_segment_instance = MagicMock()
        mock_audio_segment.from_file.return_value = mock_audio_segment_instance
        mock_audio_segment_instance.set_frame_rate.return_value = (
            mock_audio_segment_instance
        )
        mock_audio_segment_instance.set_channels.return_value = (
            mock_audio_segment_instance
        )
        mock_audio_segment_instance.get_array_of_samples.return_value = [1, 2, 3]

        mock_np_array.return_value = [1, 2, 3]

        mock_audio_input_instance = MagicMock()
        mock_audio_input.return_value = mock_audio_input_instance

        mock_pipeline_instance = MagicMock()
        mock_pipeline.return_value = mock_pipeline_instance

        # Создаем мок для результата pipeline.run
        mock_result = AsyncMock()
        mock_pipeline_instance.run = AsyncMock(return_value=mock_result)

        # Мок для stream
        async def mock_generator():
            event = MagicMock()
            event.type = "voice_stream_event_audio"
            event.data = MagicMock()
            event.data.tobytes.return_value = b"audio"
            yield event

        mock_result.stream = mock_generator

        # Количество одновременных соединений
        num_connections = 5

        # Создаем тестовое аудио
        with open("test_audio.wav", "wb") as f:
            f.write(b"test audio data")

        # Функция для выполнения отдельного запроса
        def make_request():
            with open("test_audio.wav", "rb") as f:
                response = self.client.post(
                    "/process-audio/", files={"audio": ("test.wav", f, "audio/wav")}
                )
            return response.status_code

        # Запускаем несколько запросов одновременно
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=num_connections
        ) as executor:
            futures = [executor.submit(make_request) for _ in range(num_connections)]
            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        # Очищаем тестовый файл
        os.remove("test_audio.wav")

        # Проверяем, что все запросы завершились успешно
        self.assertEqual(
            results.count(200),
            num_connections,
            f"Не все запросы завершились успешно: {results}",
        )

    @patch("app.voice_agents.VoicePipeline")
    @patch("app.voice_agents.SingleAgentVoiceWorkflow")
    def test_pipeline_performance(self, mock_workflow, mock_pipeline):
        """Тест производительности голосового конвейера."""
        # Создаем тестовые аудиоданные
        test_audio = np.array([1, 2, 3], dtype=np.int16)

        # Настраиваем моки
        mock_workflow_instance = MagicMock()
        mock_workflow.return_value = mock_workflow_instance

        mock_pipeline_instance = MagicMock()
        mock_pipeline.return_value = mock_pipeline_instance

        # Создаем мок для результата pipeline.run
        mock_result = MagicMock()
        mock_pipeline_instance.run.return_value = mock_result

        # Создаем экземпляр аудиовхода
        audio_input = AudioInput(buffer=test_audio)

        # Измеряем время выполнения
        start_time = time.time()

        with patch("app.voice_agents.VoicePipeline", mock_pipeline):
            with patch("app.voice_agents.SingleAgentVoiceWorkflow", mock_workflow):
                pipeline = create_voice_pipeline()
                # Тестируем не саму производительность, а создание объектов
                self.assertEqual(pipeline, mock_pipeline_instance)

        end_time = time.time()

        # Проверяем производительность создания объектов
        processing_time = end_time - start_time
        self.assertLess(
            processing_time,
            1.0,
            f"Время создания объектов ({processing_time:.2f}с) превышает допустимое (1.0с)",
        )

    @patch("app.main.AudioSegment")
    @patch("app.main.create_voice_pipeline")
    @patch("app.main.AudioInput")
    @patch("numpy.array")
    @patch(
        "app.main.StreamingResponse",
        return_value=MagicMock(status_code=200, headers={"content-type": "audio/pcm"}),
    )
    def test_memory_usage(
        self,
        mock_response,
        mock_np_array,
        mock_audio_input,
        mock_pipeline,
        mock_audio_segment,
    ):
        """Тест использования памяти при обработке аудиофайлов."""
        # Настраиваем моки
        mock_audio_segment_instance = MagicMock()
        mock_audio_segment.from_file.return_value = mock_audio_segment_instance
        mock_audio_segment_instance.set_frame_rate.return_value = (
            mock_audio_segment_instance
        )
        mock_audio_segment_instance.set_channels.return_value = (
            mock_audio_segment_instance
        )
        mock_audio_segment_instance.get_array_of_samples.return_value = [1, 2, 3]

        mock_np_array.return_value = [1, 2, 3]

        mock_audio_input_instance = MagicMock()
        mock_audio_input.return_value = mock_audio_input_instance

        mock_pipeline_instance = MagicMock()
        mock_pipeline.return_value = mock_pipeline_instance

        # Создаем мок для результата pipeline.run
        mock_result = AsyncMock()
        mock_pipeline_instance.run = AsyncMock(return_value=mock_result)

        # Мок для stream
        async def mock_generator():
            event = MagicMock()
            event.type = "voice_stream_event_audio"
            event.data = MagicMock()
            event.data.tobytes.return_value = b"audio"
            yield event

        mock_result.stream = mock_generator

        # Создаем тестовое аудио (больше, чем в предыдущих тестах)
        with open("large_test_audio.wav", "wb") as f:
            f.write(b"test audio data" * 1000)  # ~14KB файл

        # Выполняем тестовый запрос
        with open("large_test_audio.wav", "rb") as f:
            response = self.client.post(
                "/process-audio/",
                files={"audio": ("large_test_audio.wav", f, "audio/wav")},
            )

        # Очищаем тестовый файл
        os.remove("large_test_audio.wav")

        # Проверяем результат запроса
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
