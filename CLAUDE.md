# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Язык общения

Общаемся на русском. Технические термины и идентификаторы кода — на английском.

## Команды

```bash
uv sync                    # установить зависимости (ВСЕГДА uv, не pip)
uv sync --extra dev        # + dev-зависимости (pytest, ruff)
uv run spondex --help      # запуск CLI
uv run pytest tests/ -v    # все тесты
uv run pytest tests/test_rpc.py -v          # один файл
uv run pytest tests/test_config.py::test_save_load_round_trip_defaults -v  # один тест
uv run ruff check src/     # линтинг
```

Управление зависимостями — только через `uv` нативно (`uv add`, `uv sync`), **не** `uv pip`.

## Архитектура

Spondex — CLI-демон синхронизации музыкальных библиотек Yandex Music и Spotify.

```
CLI (typer) ──httpx──► UDS ──► FastAPI RPC Server ──► DaemonState
                              ~/.spondex/daemon.sock
```

**CLI** (`cli.py`) — тонкий клиент. Не содержит бизнес-логики. Отправляет JSON-команды демону через Unix Domain Socket (httpx с UDS-транспортом) и форматирует ответы через Rich.

**Daemon** (`daemon.py`) — double-fork daemonization. После fork: `setsid()` → второй fork → redirect stdio → PID-файл → `asyncio.run()`. Родительский процесс ждёт появления PID-файла и возвращает управление CLI.

**RPC Server** (`server/rpc.py`) — FastAPI на UDS. `DaemonState` — единый объект состояния, содержит `asyncio.Event` для shutdown. Этот же Event используется и для SIGTERM через `loop.add_signal_handler`, и для RPC-команды shutdown.

**IPC-протокол**: `POST /rpc` с JSON `{"cmd": "...", "params": {}}` → `{"ok": true, "data": {}, "error": null}`.

## Структура пакета

Исходники в `src/spondex/`, build backend — hatchling. Entry point: `spondex = "spondex.cli:app"`.

Runtime-файлы демона — в `~/.spondex/` (config.toml, daemon.pid, daemon.sock, logs/).

## Ключевые паттерны

- Config загружается/сохраняется как TOML (`tomllib` для чтения, ручная сериализация для записи)
- `get_base_dir()` из `config.py` — единственный источник пути `~/.spondex/`; в тестах монкейпатчится через фикстуру `base_dir` в `conftest.py` (патчит и `spondex.config.get_base_dir`, и `spondex.daemon.get_base_dir`)
- Daemon импортирует `create_rpc_app` и `DaemonState` лениво внутри `_async_main()` чтобы избежать circular imports

## Тестирование

- RPC тесты используют `fastapi.testclient.TestClient`
- CLI тесты используют `typer.testing.CliRunner`
- Daemon тесты не тестируют `start()` / `os.fork()` — только юнит-методы (PID, cleanup, socket)
- Фикстура `base_dir` изолирует все тесты от реальной `~/.spondex/`

## Планирование

Прогресс: `docs/progress.md`. Задачи по фазам: `docs/tasks/*.md` (чекбоксы).
