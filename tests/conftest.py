import sys
from pathlib import Path

# Модули сборщика лежат в scripts/ — подключаем к импортам тестов.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
