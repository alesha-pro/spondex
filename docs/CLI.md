# Spondex CLI Reference

Полная документация по всем командам CLI.

## Общая информация

```
spondex [COMMAND] [OPTIONS]
```

Spondex — CLI-демон, все команды взаимодействуют с фоновым процессом через Unix Domain Socket (`~/.spondex/daemon.sock`). Если демон не запущен, команды, требующие подключения, выведут ошибку.

---

## Команды управления демоном

### `spondex start`

Запустить фоновый демон. При первом запуске (если нет `~/.spondex/config.toml`) автоматически запускается мастер настройки (wizard).

```bash
spondex start
```

**Поведение:**
- Создаёт директорию `~/.spondex/` и поддиректории, если не существуют
- Если конфигурация отсутствует — запускает интерактивный wizard
- Проверяет, не запущен ли уже демон (по PID-файлу)
- Выполняет double-fork daemonization, записывает PID в `~/.spondex/daemon.pid`
- Запускает RPC-сервер на `~/.spondex/daemon.sock` и Dashboard на HTTP-порту

**Коды выхода:**
- `0` — демон запущен (или уже был запущен)
- `1` — ошибка запуска

---

### `spondex stop`

Остановить демон. Сначала пытается отправить команду `shutdown` через RPC, при неудаче — fallback на SIGTERM по PID.

```bash
spondex stop
```

**Коды выхода:**
- `0` — демон остановлен (или не был запущен)

---

### `spondex restart`

Последовательно выполняет stop + start.

```bash
spondex restart
```

---

## Мониторинг

### `spondex status`

Показать состояние демона: статус, аптайм, информацию о планировщике и счётчики треков.

```bash
spondex status
```

**Вывод включает:**
- **State** — текущее состояние (`idle`, `syncing`, `paused`, `error`)
- **Uptime** — время работы демона
- **Scheduler** — режим синхронизации, интервал, статус паузы, время последней и следующей синхронизации
- **Counters** — количество синхронизированных треков, несопоставленных треков, количество запусков синхронизации
- **Last sync** — детальная статистика последней синхронизации

---

### `spondex logs`

Показать логи демона.

```bash
spondex logs [OPTIONS]
```

**Опции:**

| Опция | Короткая | По умолчанию | Описание |
|-------|----------|-------------|----------|
| `--lines` | `-n` | `50` | Количество последних строк |
| `--follow` | `-f` | `false` | Непрерывный вывод новых строк (как `tail -f`) |
| `--sync` | — | `false` | Показать `sync.log` (JSON) вместо `daemon.log` |

**Примеры:**

```bash
# Последние 50 строк daemon.log
spondex logs

# Последние 100 строк
spondex logs -n 100

# Следить за логами в реальном времени
spondex logs -f

# JSON-лог синхронизации
spondex logs --sync

# Следить за sync-логом
spondex logs --sync -f
```

**Подсветка уровней:**
- `[error]` / `[critical]` — красный
- `[warning]` — жёлтый
- `[debug]` — приглушённый

---

### `spondex dashboard`

Открыть веб-дашборд в браузере по умолчанию.

```bash
spondex dashboard
```

Адрес: `http://127.0.0.1:<dashboard_port>` (по умолчанию порт `9847`).

Дашборд — React SPA с обновлениями в реальном времени через WebSocket, графиками и управлением треками.

---

## Синхронизация

### `spondex sync`

Запустить цикл синхронизации на работающем демоне.

```bash
spondex sync [OPTIONS]
```

**Опции:**

| Опция | Короткая | По умолчанию | Описание |
|-------|----------|-------------|----------|
| `--now / --no-now` | — | `--now` | Запустить синхронизацию немедленно |
| `--mode` | `-m` | *(из конфига)* | Режим: `full` или `incremental` |

**Примеры:**

```bash
# Запустить синхронизацию с текущими настройками
spondex sync

# Полная синхронизация (пересканировать все треки)
spondex sync --mode full

# Инкрементальная синхронизация
spondex sync -m incremental
```

**Режимы синхронизации:**
- **incremental** — синхронизирует только изменения с момента последней синхронизации (быстрее)
- **full** — полное сканирование обеих библиотек, повторное сопоставление всех треков

---

## Конфигурация

### `spondex config show`

Показать текущую конфигурацию. Секреты (токены, client_secret) отображаются как `***`.

```bash
spondex config show
```

**Пример вывода:**

```
Current Configuration

[daemon]
  dashboard_port = 9847
  log_level      = info

[sync]
  interval_minutes = 30
  mode             = incremental
  propagate_deletions = True

[spotify]
  client_id      = abc123...
  client_secret  = ***
  redirect_uri   = http://127.0.0.1:8888/callback
  refresh_token  = ***

[yandex]
  token = ***
```

---

### `spondex config set`

Задать значение конфигурации.

```bash
spondex config set <key> <value>
```

**Аргументы:**

| Аргумент | Описание |
|----------|----------|
| `key` | Ключ в формате `секция.поле` (напр. `sync.mode`) |
| `value` | Новое значение |

**Все доступные ключи:**

#### Секция `daemon`

| Ключ | Тип | По умолчанию | Описание |
|------|-----|-------------|----------|
| `daemon.dashboard_port` | `int` | `9847` | Порт веб-дашборда |
| `daemon.log_level` | `str` | `info` | Уровень логирования |

#### Секция `sync`

| Ключ | Тип | По умолчанию | Описание |
|------|-----|-------------|----------|
| `sync.interval_minutes` | `int` | `30` | Минуты между синхронизациями |
| `sync.mode` | `full` \| `incremental` | `incremental` | Режим синхронизации |
| `sync.propagate_deletions` | `bool` | `true` | Зеркалировать удаления лайков |

#### Секция `spotify`

| Ключ | Тип | По умолчанию | Описание |
|------|-----|-------------|----------|
| `spotify.client_id` | `str` | *(пусто)* | Client ID приложения Spotify |
| `spotify.client_secret` | `SecretStr` | *(пусто)* | Client Secret приложения Spotify |
| `spotify.redirect_uri` | `str` | `http://127.0.0.1:8888/callback` | OAuth redirect URI |
| `spotify.refresh_token` | `SecretStr` | *(пусто)* | OAuth refresh token |

#### Секция `yandex`

| Ключ | Тип | По умолчанию | Описание |
|------|-----|-------------|----------|
| `yandex.token` | `SecretStr` | *(пусто)* | OAuth-токен Яндекс Музыки |

**Примеры:**

```bash
# Изменить интервал синхронизации
spondex config set sync.interval_minutes 15

# Переключить режим на полный
spondex config set sync.mode full

# Отключить распространение удалений
spondex config set sync.propagate_deletions false

# Задать порт дашборда
spondex config set daemon.dashboard_port 8080

# Задать токен Yandex Music
spondex config set yandex.token <ваш_токен>

# Задать учётные данные Spotify
spondex config set spotify.client_id <client_id>
spondex config set spotify.client_secret <client_secret>
```

---

## База данных

### `spondex db status`

Показать статистику базы данных и информацию о последней синхронизации.

```bash
spondex db status
```

**Вывод включает:**
- Путь к файлу БД (`~/.spondex/spondex.db`) и его размер
- Количество записей по таблицам:
  - `track_mapping` — сопоставления треков (Spotify ↔ Yandex)
  - `collection` — коллекции (лайки / плейлисты)
  - `collection_track` — треки в коллекциях
  - `unmatched` — несопоставленные треки
  - `sync_runs` — запуски синхронизации
- Детали последней синхронизации: статус, направление, режим, время, статистика, ошибки

---

## Файлы и директории

Все runtime-файлы располагаются в `~/.spondex/`:

| Файл / Директория | Описание |
|-------------------|----------|
| `config.toml` | Конфигурация (chmod 600) |
| `daemon.pid` | PID работающего демона |
| `daemon.sock` | Unix Domain Socket для RPC |
| `spondex.db` | SQLite база данных |
| `logs/daemon.log` | Человеко-читаемые логи демона |
| `logs/sync.log` | JSON-логи синхронизации |

---

## Переменные окружения

Spondex не использует переменных окружения для конфигурации. Вся настройка производится через `~/.spondex/config.toml` или команду `spondex config set`.
