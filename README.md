# SubtitleKit - Subtitle Processing Toolkit

[![PyPI version](https://badge.fury.io/py/subtitlekit.svg)](https://badge.fury.io/py/subtitlekit)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Comprehensive Python library and desktop application for subtitle processing, synchronization, and correction.

## ✨ Features

- **Merge & Sync**: Combine subtitle files with automatic synchronization
- **Fix Overlaps**: Detect and correct timing issues and overlaps  
- **Apply Corrections**: Apply text corrections from JSON files
- **Subtitle Optimizer**: Automatic CPS optimization, line reduction, filler word removal, and AI-powered shortening (via Gemini API)
- **LLM Integration**: Generate optimized JSON for translation workflows
- **Desktop App**: Cross-platform GUI (Windows, macOS, Linux)
- **Colab Ready**: Works seamlessly in Google Colab notebooks

## 🚀 Quick Start

### Installation

```bash
pip install subtitlekit
```

### Google Colab

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/drive/1lvdSX7aNhNknLs9laxfTeKdK_xNUvLOY?usp=sharing)

```python
# Install
!pip install subtitlekit

# Launch UI
from subtitlekit.ui import show_ui
show_ui(lang='en')  # or 'el' for Greek
```

### As a Library

```python
from subtitlekit import merge_subtitles, fix_overlaps, apply_corrections

# Merge subtitle files
merge_subtitles("original.srt", ["helper.srt"], "output.json")

# Fix timing overlaps
fix_overlaps("input.srt", "reference.srt", "fixed.srt")

# Apply corrections from JSON
apply_corrections("input.srt", "corrections.json", "output.srt")
```

### CLI Usage

```bash
# Merge subtitles
subtitlekit merge --original original.srt --helper helper.srt --output output.json

# Fix overlaps
subtitlekit overlaps --input input.srt --reference ref.srt --output fixed.srt

# Apply corrections
subtitlekit corrections --input input.srt --corrections fixes.json --output corrected.srt

# Optimize subtitles
subtitlekit optimize input.srt --interjections --line-reduction --cps --llm
```

### Desktop App

Download the standalone application from [Releases](https://github.com/angelospk/subtitlekit/releases).

**Or launch programmatically:**
```python
python -m subtitlekit.ui.desktop
```

## 📖 Documentation

### Merge Subtitles

Combines original subtitle file with one or more helper files (different languages) to create JSON output optimized for LLM translation workflows.

```bash
subtitlekit merge \
  --original movie.srt \
  --helper helpful_en.srt \
  --helper helpful_pt.srt \
  --output for_translation.json \
  --skip-sync  # optional: skip ffsubsync
```

**Output format:**
```json
{
  "id": 1,
  "t": "00:00:11,878 --> 00:00:16,130",
  "trans": "Original text to translate",
  "h1": "Helper text (language 1)",
  "h2": "Helper text (language 2)"
}
```

### Fix Overlaps

Detects and corrects timing issues:
- Overlapping timestamps
- Out-of-order entries
- Unreasonable durations
- Duplicate timings

```bash
subtitlekit overlaps \
  --input problematic.srt \
  --reference correct_timings.srt \
  --output fixed.srt \
  --window 5
```

### Apply Corrections

Apply text corrections from JSON file:

```bash
subtitlekit corrections \
  --input subtitle.srt \
  --corrections fixes.json \
  --output corrected.srt
```

### Subtitle Optimizer

Automated pipeline to improve subtitle readability and timing. Supports multiple languages (English, Greek, etc.) for interjection removal.

```bash
subtitlekit optimize movie.srt \
  --interjections \
  --line-reduction \
  --cps \
  --llm \
  --api-key YOUR_GEMINI_API_KEY
```

**Optimization Phases:**
1. **Interjection Removal**: Removes filler words (e.g., "Uh,", "Well,").
2. **Line Reduction**: Collapses 3+ line entries into 2 lines for better layout.
3. **CPS Optimization**: Extends timing and merges short subtitles to hit target Characters Per Second (default: 20.0).
4. **LLM Shortening**: Uses Gemini AI to shorten entries that still exceed CPS limits.
5. **Translation Prep**: Experimental `--simplify` flag to simplify text for easier translation.

## 🌍 I18n Support

Desktop and Colab UIs support:
- 🇬🇧 English
- 🇬🇷 Greek (Ελληνικά)

## 📦 Development

```bash
# Clone repository
git clone https://github.com/angelospk/subtitlekit.git
cd subtitlekit

# Install in development mode
pip install -e .

# Install pre-commit hooks (Mandatory for contributing)
pip install pre-commit
pre-commit install

# Run tests manually
pytest -v
```

## 🤝 Contributing

Contributions are welcome! Please ensure all tests pass before submitting a Pull Request. We use `pre-commit` to enforce running `pytest` automatically before every commit to prevent breaking changes.

## 📄 License

MIT License - see [LICENSE](LICENSE) file.

## 🙏 Credits

Built by [angelospk](https://github.com/angelospk)
