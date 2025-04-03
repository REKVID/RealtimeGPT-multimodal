import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Добавляем корневую директорию проекта в sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.voice_agents import create_voice_pipeline
from agents.voice import VoicePipeline, SingleAgentVoiceWorkflow


class TestPipeline(unittest.TestCase):
    @patch("app.voice_agents.VoicePipeline")
    @patch("app.voice_agents.SingleAgentVoiceWorkflow")
    def test_create_voice_pipeline(self, mock_workflow, mock_pipeline):
        # Настройка моков
        mock_workflow_instance = MagicMock()
        mock_workflow.return_value = mock_workflow_instance

        mock_pipeline_instance = MagicMock()
        mock_pipeline.return_value = mock_pipeline_instance

        # Вызов тестируемой функции
        result = create_voice_pipeline()

        # Проверка, что был создан экземпляр SingleAgentVoiceWorkflow
        mock_workflow.assert_called_once()

        # Проверка, что был создан экземпляр VoicePipeline с правильными параметрами
        mock_pipeline.assert_called_once_with(workflow=mock_workflow_instance)

        # Проверка, что функция возвращает ожидаемый объект
        self.assertEqual(result, mock_pipeline_instance)

    def test_pipeline_structure(self):
        # Тест для проверки структуры созданного объекта
        pipeline = create_voice_pipeline()

        # Проверяем, что результат имеет правильный тип
        self.assertIsInstance(pipeline, VoicePipeline)

        # Проверяем, что workflow имеет правильный тип
        self.assertIsInstance(pipeline.workflow, SingleAgentVoiceWorkflow)


if __name__ == "__main__":
    unittest.main()
