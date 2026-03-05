import unittest
from unittest.mock import patch, mock_open
import pathlib
import llm_consortium

class TestFileReaders(unittest.TestCase):
    @patch('builtins.open', new_callable=mock_open, read_data="Test system prompt")
    @patch('pathlib.Path.parent', return_value=pathlib.Path('.'))
    def test_read_system_prompt(self, mock_path, mock_file):
        result = llm_consortium.orchestrator._read_system_prompt()
        self.assertEqual(result, "Test system prompt")
        mock_file.assert_called_once()

    @patch('builtins.open', new_callable=mock_open, read_data="Test arbiter prompt")
    @patch('pathlib.Path.parent', return_value=pathlib.Path('.'))
    def test_read_arbiter_prompt(self, mock_path, mock_file):
        result = llm_consortium.orchestrator._read_arbiter_prompt()
        self.assertEqual(result, "Test arbiter prompt")
        mock_file.assert_called_once()

    @patch('builtins.open', new_callable=mock_open, read_data="Test iteration prompt")
    @patch('pathlib.Path.parent', return_value=pathlib.Path('.'))
    def test_read_iteration_prompt(self, mock_path, mock_file):
        result = llm_consortium.orchestrator._read_iteration_prompt()
        self.assertEqual(result, "Test iteration prompt")
        mock_file.assert_called_once()

    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_read_system_prompt_file_not_found(self, mock_file):
        result = llm_consortium.orchestrator._read_system_prompt()
        self.assertEqual(result, "")

    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_read_arbiter_prompt_file_not_found(self, mock_file):
        result = llm_consortium.orchestrator._read_arbiter_prompt()
        self.assertEqual(result, "")

    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_read_iteration_prompt_file_not_found(self, mock_file):
        result = llm_consortium.orchestrator._read_iteration_prompt()
        self.assertEqual(result, "")

if __name__ == '__main__':
    unittest.main()
