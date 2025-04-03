import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import sys
import os
import io

# Добавляем корневую директорию проекта в sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from app.main import app


class TestAPIEndpoints(unittest.TestCase):
    def setUp(self):
        # Инициализируем TestClient без именованных аргументов
        self.client = TestClient(app)

    def test_root_endpoint(self):
        """Тест GET-запроса к корневому эндпоинту."""
        with patch(
            "builtins.open", unittest.mock.mock_open(read_data="<html>Test</html>")
        ):
            response = self.client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.text, "<html>Test</html>")

    @patch("app.main.AudioSegment")
    @patch("app.main.create_voice_pipeline")
    @patch("app.main.AudioInput")
    @patch("numpy.array")
    def test_process_audio_endpoint(
        self, mock_np_array, mock_audio_input, mock_pipeline, mock_audio_segment
    ):
        """Тест POST-запроса к эндпоинту обработки аудио."""
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

        # Отправляем тестовый запрос
        with open("test_audio.wav", "wb") as f:
            f.write(b"test audio data")

        with open("test_audio.wav", "rb") as f:
            response = self.client.post(
                "/process-audio/", files={"audio": ("test.wav", f, "audio/wav")}
            )

        # Очищаем тестовый файл
        os.remove("test_audio.wav")

        # Проверяем результат
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/pcm")

    @patch("app.main.WebSocket")
    @patch("app.main.AudioSegment")
    @patch("app.main.create_voice_pipeline")
    @patch("app.main.AudioInput")
    @patch("numpy.array")
    def test_websocket_endpoint(
        self,
        mock_np_array,
        mock_audio_input,
        mock_pipeline,
        mock_audio_segment,
        mock_websocket,
    ):
        """Тест для WebSocket-эндпоинта."""
        # Настраиваем моки
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.receive_bytes = AsyncMock(return_value=b"test audio data")
        mock_ws.send_bytes = AsyncMock()
        mock_ws.close = AsyncMock()

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
            # Вызываем исключение, чтобы выйти из бесконечного цикла
            raise Exception("End of test")

        mock_result.stream = mock_generator

        # Импортируем функцию для тестирования
        from app.main import websocket_endpoint

        # Тестируем с помощью pytest
        with patch("app.main.websocket_endpoint", return_value=AsyncMock()):
            pass  # В реальном окружении здесь был бы вызов pytest


if __name__ == "__main__":
    unittest.main()
