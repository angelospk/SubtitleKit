# SubtitleKit - Subtitle Processing Toolkit

Comprehensive Python library and desktop application for subtitle processing, synchronization, and correction.

## Features

- **Merge & Sync**: Combine subtitle files with automatic synchronization
- **Fix Overlaps**: Detect and correct timing issues and overlaps
- **Apply Corrections**: Apply text corrections from JSON files
- **LLM Integration**: Generate optimized JSON for translation workflows

## Installation

```bash
pip install subtitlekit
```

## Quick Start

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
```

### Desktop App

Download the standalone application from [Releases](https://github.com/angelospk/subtitlekit/releases).

## Documentation

See the full documentation in the [docs](docs/) directory.

## Development

```bash
# Clone repository
git clone https://github.com/angelospk/subtitlekit.git
cd subtitlekit

# Install in development mode
pip install -e .

# Run tests
pytest -v
```

## License

MIT License - see [LICENSE](LICENSE) file.
