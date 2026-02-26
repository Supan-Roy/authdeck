# AuthDeck

Professional desktop TOTP authenticator for Windows built with Python + PyQt6.

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
- Local secrets file (`data/accounts.json`) is git-ignored.
