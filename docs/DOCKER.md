# Spondex в Docker

Образ запускает демон в foreground (`spondex run`): без double-fork, логи идут в stdout (`docker logs`) и в `/data/logs/`.
Все runtime-файлы (`config.toml`, `spondex.db`, `logs/`, `daemon.sock`) лежат в volume `/data`.

## Файлы

| Файл | Назначение |
|------|------------|
| `Dockerfile` | multi-stage: сборка дашборда (node) → uv sync → slim runtime, пользователь `UID:GID` (по умолчанию 1000) |
| `compose.yaml` | сервис `spondex`, `restart: unless-stopped`, volume `./data:/data`, порт дашборда |
| `.env.example` | шаблон `.env` (интерфейс/порт дашборда, каталог данных, UID/GID, TZ) |

## Запуск

Склонируйте репозиторий на хост с Docker и в его корне выполните:

```bash
cp .env.example .env          # при необходимости поправьте
mkdir -p data                 # владелец должен совпадать с SPONDEX_UID/SPONDEX_GID
docker compose up -d --build
```

## Первая настройка (headless)

На сервере, в каталоге деплоя:

```bash
docker compose run --rm -it spondex spondex setup
docker compose restart
```

Мастер работает в headless-режиме (`SPONDEX_HEADLESS=1` выставлен в образе):

1. Введите Spotify Client ID / Secret и Redirect URI (тот же, что в Spotify Developer Dashboard, например `http://127.0.0.1:8888/callback`).
2. Откройте напечатанную ссылку в браузере на любом устройстве и разрешите доступ.
3. Браузер перейдёт на redirect URI и, скорее всего, покажет ошибку соединения — это нормально. Скопируйте URL из адресной строки (с `?code=...`) и вставьте в терминал.
4. Яндекс Музыка: выберите `device` — мастер покажет адрес и код, введите код на странице Яндекса (с любого устройства). Токен будет продлеваться автоматически.
5. Задайте параметры синхронизации.

Перезаписать существующий конфиг: `spondex setup --force`.

## Токены

- **Spotify:** хранится `refresh_token`, access token обновляется сам. Если Spotify выдаст новый `refresh_token`, он сохраняется в `config.toml`.
- **Яндекс (вход по коду):** токен продлевается автоматически за 30 дней до истечения или если Яндекс его отклонил; новые токены сохраняются в `config.toml`.

Если доступ всё же отозван (сменили пароль, отозвали приложение, закончился Premium у Spotify) — в логах будет подсказка. Повторный вход:

```bash
docker compose exec -it spondex spondex auth yandex     # или spotify
docker compose restart
```

## Повседневные команды

```bash
docker compose exec spondex spondex status
docker compose exec spondex spondex sync
docker compose exec spondex spondex config set sync.interval_minutes 15
docker compose restart          # применить изменения конфига
docker compose logs -f
```

`spondex start` / `restart` внутри контейнера не нужны: жизненным циклом управляет Docker. `spondex stop` завершает процесс, и Docker перезапускает контейнер.

## Дашборд

У дашборда нет аутентификации, поэтому он публикуется только на приватный интерфейс, заданный в `.env`:

```dotenv
SPONDEX_BIND=100.64.0.10    # например, Tailscale IP хоста; по умолчанию 127.0.0.1
SPONDEX_PORT=9847
```

> Если Docker стартует при загрузке раньше, чем Tailscale получит IP, контейнер не сможет занять порт на этом адресе.
> Альтернатива без этой проблемы: `SPONDEX_BIND=127.0.0.1` + `tailscale serve --bg --https=9847 http://127.0.0.1:9847`.

## Переменные окружения

| Переменная | По умолчанию (в образе) | Описание |
|------------|-------------------------|----------|
| `SPONDEX_HOME` | `/data` | Каталог runtime-файлов (вне Docker — `~/.spondex`) |
| `SPONDEX_DASHBOARD_HOST` | `0.0.0.0` | Адрес, на котором слушает дашборд (вне Docker — `127.0.0.1`) |
| `SPONDEX_HEADLESS` | `1` | Мастер не открывает браузер, redirect URL вставляется вручную |
