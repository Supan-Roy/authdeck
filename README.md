# AuthDeck

![Version](https://img.shields.io/badge/version-1.0.4-2563eb)
![Platform](https://img.shields.io/badge/platform-Windows-0ea5e9)
![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![UI](https://img.shields.io/badge/UI-PyQt6-41CD52)
![Build](https://img.shields.io/badge/build-PyInstaller-6D28D9)
![Security](https://img.shields.io/badge/backup-AES--256--GCM-059669)

Professional desktop TOTP authenticator for Windows built with Python + PyQt6.

## Download

- https://www.supanroy.com/projects/authdeck-download

## Author

- Developer: Supan Roy
- Email: support@supanroy.com

## Features

- Add account by screen-region QR scan or manual entry
- Parses `otpauth://` URLs automatically
- Generates 6-digit TOTP codes with 30-second refresh
- Copy code from main panel, sidebar context menu, or tray menu
- Dark/light theme switch
- Import/export backup JSON
- Minimize-to-tray workflow

## Run from source

```powershell
pip install -r requirements.txt
python main.py
```

## Build executable

```powershell
.\scripts\build.ps1
```

Output: `dist/AuthDeck.exe`

## Build installer

```powershell
.\scripts\build-installer.ps1
```

Output: `installer/output/AuthDeck-Setup.exe`

## Security notes

- Accounts are stored locally only.
- App PIN is stored as salted PBKDF2 hash.
- Backup exports are encrypted with a user password (AES-256-GCM + PBKDF2 key derivation).