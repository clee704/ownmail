"""Tests for __main__.py entry point."""

import runpy
import sys
from unittest.mock import patch


class TestMainModule:
    """Tests for __main__.py module."""

    def test_main_imports_cli(self):
        """Test that __main__ imports from cli module."""
        # Verify the import works
        from ownmail.__main__ import main
        assert callable(main)

    def test_runpy_finds_module(self):
        """Test that python -m ownmail can find the module."""
        # This tests that the package is set up correctly
        with patch.object(sys, 'argv', ['ownmail', '--help']):
            with patch('ownmail.cli.main') as mock_main:
                mock_main.side_effect = SystemExit(0)
                try:
                    runpy.run_module('ownmail', run_name='__main__')
                except SystemExit:
                    pass
                # Should have tried to call main
                mock_main.assert_called_once()
