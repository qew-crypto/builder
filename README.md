# Telegram GitHub Builder v2 — без Docker

Закрытый Telegram-бот для сборки `.jar` и `.apk` из ZIP через приватный репозиторий и GitHub Actions.

## Что изменено

- Docker полностью удалён.
- После загрузки ZIP появляются кнопки **Автоматически** и **Вручную**.
- Автоматический режим ищет:
  - `build`;
  - `build.sh`;
  - `gradlew`;
  - `build.gradle` / `build.gradle.kts`;
  - `mvnw`;
  - `pom.xml`.
- Android Gradle определяется по `com.android.application`, `com.android.library` или блоку `android`.
- Ручной режим принимает:
  - shell-команды обычным сообщением;
  - файл `build`, `build.sh`, `build.gradle`, `build.gradle.kts`, `pom.xml`;
  - другой текстовый файл как shell-скрипт.
- Результат ищется автоматически среди `.jar` и `.apk`.
- `FERNET_KEY` вручную больше не требуется: при первом запуске создаётся `data/fernet.key`.

## Требования

- Python 3.11 или новее;
- Git в PATH;
- Windows, Linux или обычный VPS;
- GitHub classic PAT с правами `repo` и `workflow`.

## Настройка

Скопируйте:

```text
.env.example -> .env
```

Заполните `.env`:

```env
TELEGRAM_BOT_TOKEN=токен_от_BotFather
ALLOWED_TELEGRAM_IDS=ваш_цифровой_Telegram_ID
DATA_DIR=data
MAX_ARCHIVE_MB=45
DELETE_REPO_AFTER_BUILD=false
```

Несколько разрешённых пользователей:

```env
ALLOWED_TELEGRAM_IDS=123456789,987654321
```

Не добавляйте неправильный `FERNET_KEY`. Лучше вообще не указывать его: бот сам создаст корректный ключ в `data/fernet.key`. Не удаляйте этот файл после подключения GitHub.

## Windows

Установите Python и Git, затем запустите:

```text
start.bat
```

Скрипт сам создаст `.venv` и установит зависимости.

## Linux / VPS

```bash
chmod +x start.sh
./start.sh
```

Либо вручную:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

## Использование

1. `/start`.
2. **Подключить GitHub**.
3. Ввести GitHub-логин и classic PAT.
4. **Загрузить ZIP**.
5. Выбрать:
   - **Автоматически** — бот сам найдёт способ сборки;
   - **Вручную** — вставить команды или отправить build-файл.
6. Дождаться результата.

Пример ручных команд для Fabric:

```bash
chmod +x gradlew
./gradlew --no-daemon build
```

Пример для Android:

```bash
chmod +x gradlew
./gradlew --no-daemon assembleDebug
```

Можно использовать многострочные команды, `cd`, переменные окружения и другие обычные команды Bash GitHub Runner.

## Безопасность

- доступ проверяется по Telegram ID;
- GitHub PAT хранится в SQLite в зашифрованном виде;
- PAT не добавляется в сборочный репозиторий;
- пользовательские `.github/workflows` из ZIP удаляются;
- защита от `../`, символьных ссылок и ZIP bomb;
- репозитории создаются приватными.

Ручные команды и Gradle-скрипты выполняют произвольный код на GitHub Runner. Добавляйте только доверенные Telegram ID.
