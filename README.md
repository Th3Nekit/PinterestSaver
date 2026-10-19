<p align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset=".github/expressive/header-dark.svg">
  <img src=".github/expressive/header-light.svg" width="100%" alt="PinterestSaver — проект Th3Nekit">
</picture>
</p>

# PinterestSaver

> [English version](README_EN.md)

Простая программа с GUI — вставляешь ссылки на пины Pinterest, выбираешь папку — и она скачивает все картинки в лучшем качестве.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Flet](https://img.shields.io/badge/Flet-0.28%2B-02569B?logo=flutter&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)

## Возможности

- **Батч-скачивание** — вставь ссылки на пины (по одной в строке) и скачай все разом
- **Лучшее качество** — выбирает самую большую картинку из ответа Pinterest API
- **Выбор папки** — сохраняй куда угодно
- **GUI** — современный интерфейс на Flet

## Стек

- [Flet](https://flet.dev/) — кросс-платформенный GUI на Flutter
- Pinterest JSON API — публичный endpoint для получения данных пинов

## Установка и запуск

```bash
pip install -r requirements.txt
python main.py
```

## Сборка в EXE

```bash
flet pack main.py --name PinterestSaver
```

## Структура

```
PinterestSaver/
├── main.py              # Основной файл (GUI + логика)
├── requirements.txt     # Зависимости
└── PinterestSaver.spec  # Конфиг PyInstaller
```

## Автор

[@th3_nek1t](https://t.me/th3_nek1t)

## Лицензия

MIT © 2026 Th3Nekit

