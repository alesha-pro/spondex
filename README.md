# Spondex

CLI-демон для синхронизации музыкальных библиотек между **Spotify** и **Яндекс Музыкой**.

Spondex работает в фоне как демон и периодически синхронизирует любимые треки между платформами. Новые лайки с любой стороны автоматически переносятся на другую с учётом нечёткого сопоставления, транслитерации и проверки длительности.

## Установка

```bash
# Клонировать и установить через uv
git clone <repo-url> && cd spondex
uv sync
```

## Быстрый старт

```bash
# Первый запуск — запускает мастер настройки
spondex start

# Проверить статус
spondex status

# Запустить синхронизацию сразу
spondex sync --now

# Смотреть логи
spondex logs -f

# Открыть веб-дашборд
spondex dashboard

# Остановить демон
spondex stop
```

## Команды

| Команда                              | Описание                                              |
| ------------------------------------ | ----------------------------------------------------- |
| `spondex start`                      | Запустить демон (при первом запуске — мастер настройки) |
| `spondex stop`                       | Остановить демон корректно                            |
| `spondex restart`                    | Остановить и снова запустить                          |
| `spondex status`                     | Состояние, аптайм, планировщик, счётчики треков        |
| `spondex sync [--mode full]`         | Запустить цикл синхронизации                          |
| `spondex logs [-n 50] [-f]`         | Вывод логов демона                                    |
| `spondex logs --sync`                | JSON-лог синхронизации                                |
| `spondex dashboard`                  | Открыть веб-дашборд в браузере                        |
| `spondex config show`                | Текущая конфигурация (секреты скрыты)                 |
| `spondex config set <key> <val>`     | Задать значение (напр. `sync.mode full`)              |
| `spondex db status`                  | Статистика БД и данные последней синхронизации         |

## Конфигурация

Конфигурация хранится в `~/.spondex/config.toml` и создаётся мастером настройки при первом запуске `spondex start`.

```bash
# Просмотр
spondex config show

# Изменение
spondex config set sync.interval_minutes 15
spondex config set sync.mode full
spondex config set spotify.refresh_token <token>
spondex config set yandex.token <token>
```

### Секции

- **daemon** — `dashboard_port`, `log_level`
- **sync** — `interval_minutes`, `mode` (full/incremental), `propagate_deletions`
- **spotify** — `client_id`, `client_secret`, `redirect_uri`, `refresh_token`
- **yandex** — `token`

## Архитектура

```
CLI (typer)
  │
  │  httpx (UDS)
  ▼
FastAPI RPC Server ──► DaemonState
  │  ~/.spondex/daemon.sock       │
  │                               ├── SyncEngine
  │                               ├── SyncScheduler
  │                               └── Database (SQLite)
  │
Dashboard Server (Starlette + React SPA)
  │  http://127.0.0.1:9847
```

**CLI** — тонкий клиент, отправляющий JSON-команды через Unix domain socket.

**Daemon** — даемонизация через double-fork с PID-файлом, обработкой сигналов и структурированным логированием (structlog → RotatingFileHandler).

**RPC Server** — FastAPI на UDS. Все команды идут через `POST /rpc` с телом `{"cmd": "...", "params": {}}`.

**Sync Engine** — двунаправленная синхронизация с трёхуровневым нечётким сопоставлением (нормализация, транслитерация, fuzzy с проверкой длительности). Режимы full и incremental.

**Dashboard** — React SPA на Starlette с обновлениями по WebSocket в реальном времени, графиками и управлением треками.

## Разработка

```bash
# Установить dev-зависимости
uv sync --extra dev

# Запустить тесты
uv run pytest tests/ -v

# Тесты с покрытием
uv run pytest tests/ --cov=spondex --cov-report=term-missing

# Линтинг
uv run ruff check src/ tests/

# Форматирование
uv run ruff format src/ tests/

# Проверка типов
uv run mypy src/
```

## Безопасность

- Файл конфигурации (`~/.spondex/config.toml`) создаётся с правами `chmod 600`
- Выводится предупреждение, если права на конфиг слишком открытые
- Демон выставляет `umask(0o077)` — все runtime-файлы (сокет, логи) доступны только владельцу
- API-токены хранятся как `SecretStr` и не попадают в логи и вывод CLI
