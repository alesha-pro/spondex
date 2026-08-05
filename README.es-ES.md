

# 🎵 Spondex

**Sincronización bidireccional de bibliotecas musicales entre Spotify y Yandex Music**



[Instalación](#-instalación) • [Inicio rápido](#-inicio-rápido) • [Comandos](#-comandos) • [Configuración](#⚙️-configuración) • [Arquitectura](#-arquitectura) • [Desarrollo](#-desarrollo)

---

> ⚡ **Importante:** El proyecto ha sido completamente reescrito desde cero. La versión anterior de la aplicación está disponible en el archivo: [alesha-pro/spondex-archive](https://github.com/alesha-pro/spondex-archive)



Spondex funciona en segundo plano como un demonio y sincroniza periódicamente los *likes* (me gusta) entre plataformas. Las nuevas canciones de cualquier lado se transfieren automáticamente al otro, teniendo en cuenta la coincidencia difusa (*fuzzy matching*), la transliteración y la verificación de duración.

> 💡 Te gustó una canción en Spotify — aparecerá en Yandex Music. Y viceversa.

## 📋 Requisitos

- **Python** 3.12+
- **[uv](https://docs.astral.sh/uv/)** — gestor de paquetes y entornos
- **macOS / Linux** — soporte nativo
- **Windows** — solo a través de WSL *(no probado)*

### Instalación de uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# o a través de Homebrew
brew install uv
```

## 📦 Instalación

```bash
# Instalación global — un solo comando
uv tool install spondex

# O desde el código fuente
git clone https://github.com/alesha-pro/spondex.git && cd spondex
uv sync
```

## 🚀 Inicio rápido

```bash
spondex start       # Primer lanzamiento → asistente de configuración
spondex status      # Verificar estado
spondex sync        # Ejecutar sincronización
spondex logs -f     # Seguir los registros (logs)
spondex dashboard   # Abrir panel web
spondex stop        # Detener el demonio
```

## 📋 Comandos


| Comando                          | Descripción                                                |
| -------------------------------- | ------------------------------------------------------- |
| `spondex start`                  | Iniciar demonio (en el primer lanzamiento — asistente de configuración) |
| `spondex stop`                   | Detener el demonio correctamente                              |
| `spondex restart`                | Reiniciar demonio                                     |
| `spondex status`                 | Estado, tiempo en línea, programador, contadores de canciones         |
| `spondex sync [--mode full]`     | Ejecutar ciclo de sincronización                            |
| `spondex logs [-n 50] [-f]`      | Mostrar registros del demonio                                      |
| `spondex logs --sync`            | Registro JSON de sincronización                                  |
| `spondex dashboard`              | Abrir panel web en el navegador                          |
| `spondex config show`            | Configuración actual (secretos ocultos)                   |
| `spondex config set <key> <val>` | Establecer valor (ej. `sync.mode full`)                |
| `spondex db status`              | Estadísticas de BD y datos de la última sincronización          |


Documentación detallada: [docs/CLI.md](docs/CLI.md)

## ⚙️ Configuración

### Requisitos previos

Antes del primer lanzamiento, se necesitarán las credenciales de ambos servicios. El asistente de configuración las solicitará de forma interactiva.

🟡 Token de Yandex Music

El token OAuth se puede obtener a través del navegador (DevTools) o siguiendo las instrucciones:

- [Obtención del token de Yandex Music](https://yandex-music.readthedocs.io/en/main/token.html)

```bash
spondex config set yandex.token <tu_token>
```



🟢 Configuración de la aplicación de Spotify

1. Abre [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/)
2. Crea una nueva aplicación (Create app)
3. Copia **Client ID** y **Client Secret**
4. En **Redirect URIs** agrega: `http://127.0.0.1:8888/callback`
5. Guarda los cambios

```bash
spondex config set spotify.client_id <client_id>
spondex config set spotify.client_secret <client_secret>
spondex config set spotify.redirect_uri "http://127.0.0.1:8888/callback"
```

En el primer lanzamiento, el asistente abrirá el navegador para la autorización y guardará automáticamente el `refresh_token`.



### Configuración

Se almacena en `~/.spondex/config.toml`, se crea automáticamente en el primer `spondex start`.

```bash
spondex config show                          # ver
spondex config set sync.interval_minutes 15  # modificar
```


| Sección      | Parámetros                                                            |
| ----------- | -------------------------------------------------------------------- |
| **daemon**  | `dashboard_port`, `log_level`                                        |
| **sync**    | `interval_minutes`, `mode` (full/incremental), `propagate_deletions` |
| **spotify** | `client_id`, `client_secret`, `redirect_uri`, `refresh_token`        |
| **yandex**  | `token`                                                              |


## 🏗 Arquitectura

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


| Componente       | Rol                                                            |
| --------------- | --------------------------------------------------------------- |
| **CLI**         | Cliente ligero — comandos JSON a través de Unix Domain Socket           |
| **Daemon**      | Daemonización doble-fork, archivo PID, manejo de señales, structlog |
| **RPC Server**  | FastAPI en UDS, `POST /rpc {"cmd": "...", "params": {}}`        |
| **Sync Engine** | Sincronización bidireccional con coincidencia difusa de 3 niveles      |
| **Dashboard**   | React SPA, actualizaciones WebSocket, gráficos, gestión de canciones    |


### 🎯 Algoritmo de emparejamiento de canciones

```
Nivel 1 → Normalización (minúsculas, eliminar feat/remix, quitar acentos)
Nivel 2 → Transliteración (cirílico ↔ latino)
Nivel 3 → Coincidencia difusa (Levenshtein) + verificación de duración (±5 seg)
```

## 🛠 Desarrollo

```bash
uv sync --extra dev                    # dependencias de desarrollo
uv run pytest tests/ -v                # pruebas
uv run pytest tests/ --cov=spondex     # cobertura
uv run ruff check src/ tests/          # linting
uv run ruff format src/ tests/         # formateo
uv run mypy src/                       # verificación de tipos
```

### Compilación del paquete

```bash
bash scripts/build.sh    # frontend → wheel
```

## 🔒 Seguridad

- La configuración `~/.spondex/config.toml` se crea con permisos `600`
- Advertencia si los permisos son demasiado abiertos
- El demonio establece `umask(0o077)`: todos los archivos de ejecución son accesibles solo por el propietario
- Los tokens de API se almacenan como `SecretStr` y no aparecen en los registros ni en la salida de la CLI

## 📄 Licencia

[MIT](LICENSE)
