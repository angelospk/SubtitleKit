# Building Executables Locally

Για να δοκιμάσεις το build process τοπικά πριν το push:

## Quick Build

```bash
# Install PyInstaller
pip install pyinstaller

# Build executable (simple)
pyinstaller --onefile --windowed --name SubtitleKit src/subtitlekit/ui/desktop.py

# Output: dist/SubtitleKit (or SubtitleKit.exe on Windows)
```

## Advanced Build (με locale files)

```bash
# Using the spec file
pyinstaller SubtitleKit.spec

# Test the executable
./dist/SubtitleKit  # macOS/Linux
./dist/SubtitleKit.exe  # Windows
```

## Τι Περιλαμβάνει το Workflow

### Trigger Events:
- ✅ **On Release**: Αυτόματο build όταν δημιουργείς νέο release στο GitHub
- ✅ **Manual**: Μπορείς να το τρέξεις χειροκίνητα από το Actions tab

### Builds:
- 🪟 **Windows**: `SubtitleKit.exe`
- 🍎 **macOS**: `SubtitleKit`
- 🐧 **Linux**: `SubtitleKit`

### Output Location:
Τα executables ανεβαίνουν:
1. Ως **artifacts** (για testing) - διαθέσιμα για 90 μέρες
2. Ως **release assets** (για download) - μόνιμα με το release

## Πώς να Δημιουργήσεις Release

```bash
# 1. Tag the version
git tag v0.1.0
git push origin v0.1.0

# 2. Create release on GitHub
# Στο GitHub UI: Releases → Draft new release → Choose tag v0.1.0
```

Μόλις δημιουργηθεί το release:
- ✅ PyPI workflow ανεβάζει στο `pip install subtitlekit`
- ✅ Build workflow δημιουργεί executables για κάθε OS
- ✅ Executables ανεβαίνουν αυτόματα στο release

## Testing Builds

```bash
# After download
chmod +x SubtitleKit  # macOS/Linux only
./SubtitleKit

# Windows - just double click .exe
```

## Προσοχή σε macOS

Τα unsigned executables μπορεί να δείξουν warning. Ο χρήστης πρέπει:
```
Right-click → Open → Open anyway
```

Για signed executables χρειάζεται Apple Developer account (πληρωμένο).
