

# 🎵 Spondex

**Двусторонняя синхронизация музыкальных библиотек между Spotify и Яндекс Музыкой**



[Установка](#-установка) • [Быстрый старт](#-быстрый-старт) • [Команды](#-команды) • [Настройка](#%EF%B8%8F-настройка) • [Архитектура](#-архитектура) • [Разработка](#-разработка)

---

> ⚡ **Важно:** Проект полностью переработан с нуля. Старая версия приложения доступна в архиве: [alesha-pro/spondex-archive](https://github.com/alesha-pro/spondex-archive)



Spondex работает в фоне как daemon и периодически синхронизирует лайки между платформами. Новые треки с любой стороны автоматически переносятся на другую — с учётом нечёткого сопоставления, транслитерации и проверки длительности.

> 💡 Лайкнул трек в Spotify — он появится в Яндекс Музыке. И наоборот.

## 📋 Требования

- **Python** 3.12+
- **[uv](https://docs.astral.sh/uv/)** — менеджер пакетов и окружений
- **macOS / Linux** — нативная поддержка
- **Windows** — только через WSL *(не протестировано)*

### Установка uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# или через Homebrew
brew install uv
```

## 📦 Установка

```bash
# Глобальная установка — одна команда
uv tool install spondex

# Или из исходников
git clone https://github.com/alesha-pro/spondex.git && cd spondex
uv sync
```

### Docker

```bash
cp .env.example .env
docker compose run --rm -it spondex spondex setup   # headless-мастер
docker compose up -d
```

Подробнее: [docs/DOCKER.md](docs/DOCKER.md)

## 🚀 Быстрый старт

```bash
spondex start       # Первый запуск → мастер настройки
spondex status      # Проверить статус
spondex sync        # Запустить синхронизацию
spondex logs -f     # Следить за логами
spondex dashboard   # Открыть веб-дашборд
spondex stop        # Остановить демон
```

## 📋 Команды


| Команда                          | Описание                                                |
| -------------------------------- | ------------------------------------------------------- |
| `spondex start`                  | Запустить демон (при первом запуске — мастер настройки) |
| `spondex stop`                   | Остановить демон корректно                              |
| `spondex restart`                | Перезапустить демон                                     |
| `spondex status`                 | Состояние, аптайм, планировщик, счётчики треков         |
| `spondex sync [--mode full]`     | Запустить цикл синхронизации                            |
| `spondex logs [-n 50] [-f]`      | Вывод логов демона                                      |
| `spondex logs --sync`            | JSON-лог синхронизации                                  |
| `spondex dashboard`              | Открыть веб-дашборд в браузере                          |
| `spondex config show`            | Текущая конфигурация (секреты скрыты)                   |
| `spondex config set <key> <val>` | Задать значение (напр. `sync.mode full`)                |
| `spondex db status`              | Статистика БД и данные последней синхронизации          |


Подробная документация: [docs/CLI.md](docs/CLI.md)

## ⚙️ Настройка

### Предварительные требования

Перед первым запуском понадобятся учётные данные обоих сервисов. Мастер настройки запросит их интерактивно.

🟡 Токен Яндекс Музыки

OAuth-токен можно получить через браузер (DevTools) или по инструкции:

- [Получение токена Yandex Music](https://yandex-music.readthedocs.io/en/main/token.html)

```bash
spondex config set yandex.token <ваш_токен>
```



🟢 Настройка приложения Spotify

1. Откройте [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/)
2. Создайте новое приложение (Create app)
3. Скопируйте **Client ID** и **Client Secret**
4. В **Redirect URIs** добавьте: `http://127.0.0.1:8888/callback`
5. Сохраните изменения

```bash
spondex config set spotify.client_id <client_id>
spondex config set spotify.client_secret <client_secret>
spondex config set spotify.redirect_uri "http://127.0.0.1:8888/callback"
```

При первом запуске wizard откроет браузер для авторизации и сохранит `refresh_token` автоматически.



### Конфигурация

Хранится в `~/.spondex/config.toml`, создаётся автоматически при первом `spondex start`.

```bash
spondex config show                          # просмотр
spondex config set sync.interval_minutes 15  # изменение
```


| Секция      | Параметры                                                            |
| ----------- | -------------------------------------------------------------------- |
| **daemon**  | `dashboard_port`, `log_level`                                        |
| **sync**    | `interval_minutes`, `mode` (full/incremental), `propagate_deletions` |
| **spotify** | `client_id`, `client_secret`, `redirect_uri`, `refresh_token`        |
| **yandex**  | `token`                                                              |


## 🏗 Архитектура

```
                    ┌─────────────────────────────────────────┐
                    │              Daemon Process              │
                    │                                         │
CLI (typer) ──UDS──►│  FastAPI RPC    ──► SyncEngine          │
                    │  /rpc               ├ SpotifyClient     │
                    │                     ├ YandexClient       │
                    │                     └ Database (SQLite)  │
                    │                                         │
                    │  Dashboard (React SPA)                   │
                    │  :9847  ──► WebSocket (real-time)        │
                    └─────────────────────────────────────────┘
```


| Компонент       | Роль                                                            |
| --------------- | --------------------------------------------------------------- |
| **CLI**         | Тонкий клиент — JSON-команды через Unix Domain Socket           |
| **Daemon**      | Double-fork daemonization, PID-файл, signal handling, structlog |
| **RPC Server**  | FastAPI на UDS, `POST /rpc {"cmd": "...", "params": {}}`        |
| **Sync Engine** | Двунаправленная синхронизация с 3-уровневым fuzzy matching      |
| **Dashboard**   | React SPA, WebSocket-обновления, графики, управление треками    |


### 🎯 Алгоритм сопоставления треков

```
Tier 1 → Нормализация (lowercase, strip feat/remix, убрать акценты)
Tier 2 → Транслитерация (кириллица ↔ латиница)
Tier 3 → Fuzzy matching (Levenshtein) + проверка длительности (±5 сек)
```

## 🛠 Разработка

```bash
uv sync --extra dev                    # dev-зависимости
uv run pytest tests/ -v                # тесты
uv run pytest tests/ --cov=spondex     # покрытие
uv run ruff check src/ tests/          # линтинг
uv run ruff format src/ tests/         # форматирование
uv run mypy src/                       # проверка типов
```

### Сборка пакета

```bash
bash scripts/build.sh    # фронтенд → wheel
```

## 🔒 Безопасность

- Конфиг `~/.spondex/config.toml` создаётся с правами `600`
- Предупреждение при слишком открытых правах
- Демон выставляет `umask(0o077)` — все runtime-файлы доступны только владельцу
- API-токены хранятся как `SecretStr` и не попадают в логи и вывод CLI

## 📄 Лицензия

[MIT](LICENSE)