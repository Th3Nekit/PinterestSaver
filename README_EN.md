# PinterestSaver

> [Русская версия](README.md)

Simple GUI app — paste Pinterest pin links, choose a folder, and it downloads all images in the best quality.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Flet](https://img.shields.io/badge/Flet-0.28%2B-02569B?logo=flutter&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Batch download** — paste pin links (one per line) and download all at once
- **Best quality** — picks the largest image from Pinterest API response
- **Folder picker** — save anywhere
- **GUI** — modern interface built with Flet

## Stack

- [Flet](https://flet.dev/) — cross-platform Flutter-based GUI
- Pinterest JSON API — public endpoint for pin data

## Installation & Running

```bash
pip install -r requirements.txt
python main.py
```

## Build to EXE

```bash
flet pack main.py --name PinterestSaver
```

## Structure

```
PinterestSaver/
├── main.py              # Main file (GUI + logic)
├── requirements.txt     # Dependencies
└── PinterestSaver.spec  # PyInstaller config
```

## Author

[@th3_nek1t](https://t.me/th3_nek1t)

## License

MIT © 2026 Th3Nekit
