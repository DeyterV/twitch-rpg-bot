"""
Настройка тестового окружения: подмена внешних зависимостей до импорта rpg_bot.
Этот файл загружается pytest автоматически раньше любого тестового модуля.
"""

import os
import sys
import types

# Переменные окружения вместо реального .env
os.environ['TOKEN'] = 'fake_token'
os.environ['CHANNEL'] = 'test_channel'
os.environ['SAVE_FILE'] = '__nonexistent_players_test__.json'

# dotenv — no-op, чтобы не перезаписать тестовые переменные
_dotenv_mod = types.ModuleType('dotenv')
_dotenv_mod.load_dotenv = lambda *a, **kw: None
sys.modules['dotenv'] = _dotenv_mod

# filelock
class _MockFileLock:
    def __init__(self, path): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass

_filelock_mod = types.ModuleType('filelock')
_filelock_mod.FileLock = _MockFileLock
sys.modules['filelock'] = _filelock_mod

# twitchio
def _mock_command(*args, **kwargs):
    return lambda f: f

class _MockCommandsBot:
    def __init__(self, *a, **kw): pass
    def run(self): pass

_twitchio_commands = types.ModuleType('twitchio.ext.commands')
_twitchio_commands.Bot = _MockCommandsBot
_twitchio_commands.command = _mock_command

_twitchio_ext = types.ModuleType('twitchio.ext')
_twitchio_ext.commands = _twitchio_commands

_twitchio = types.ModuleType('twitchio')
_twitchio.ext = _twitchio_ext

sys.modules['twitchio'] = _twitchio
sys.modules['twitchio.ext'] = _twitchio_ext
sys.modules['twitchio.ext.commands'] = _twitchio_commands
