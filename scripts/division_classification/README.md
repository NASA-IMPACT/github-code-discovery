# Division Classification

Classifies GitHub repository READMEs into NASA research divisions using an LLM-based agent.

## NASA Divisions

The classifier categorizes repositories into these divisions:

1. **Earth Science Division** - Satellite/ground-based Earth observation, climate, natural hazards
2. **Planetary Science Division** - Planets, moons, asteroids, comets exploration
3. **Astrophysics Division** - Universe origin, evolution, cosmic structures
4. **Heliophysics Division** - Sun, solar wind, space weather
5. **Biological and Physical Sciences Division** - Microgravity research, space biology
6. **Not a NASA Division** - Repositories not relevant to NASA research

## Requirements

- `OPENAI_API_KEY` in `.env`
- Dependencies: `pydantic-ai`, `pandas`, `loguru`, `click`

## Usage

### Classify READMEs

```bash
# Basic usage - appends results to ./data/results_cache.csv
python scripts/division_classification/classify.py classify input.csv

# Custom column names
python scripts/division_classification/classify.py classify input.csv \
    --text-column readme \
    --url-column url

# Save to specific output file
python scripts/division_classification/classify.py classify input.csv -o results.csv

# Use a different model
python scripts/division_classification/classify.py classify input.csv -m gpt-4.1

# Skip confirmation prompt (for automation)
python scripts/division_classification/classify.py classify input.csv -y

# Limit number of READMEs to classify
python scripts/division_classification/classify.py classify input.csv -l 10

# Skip duplicate checking against cache
python scripts/division_classification/classify.py classify input.csv --skip-cache-check
```

### View Statistics

```bash
# Show classification breakdown from cache
python scripts/division_classification/classify.py stats

# Use custom cache path
python scripts/division_classification/classify.py stats --cache-path ./my_results.csv
```

### List Divisions

```bash
python scripts/division_classification/classify.py divisions
```

## Input CSV Format

The input CSV must contain columns for:
- Repository URL (default column: `repo_url`)
- README text (default column: `readme_text`)

Example:
```csv
repo_url,readme_text
https://github.com/org/repo,"# My Project\nThis is a climate modeling tool..."
```

## Output

Results are saved with these columns:
- `URL` - Repository URL
- `text` - README content
- `area` - Classified NASA division
- `reasoning` - Explanation for classification
- `source` - Source label (configurable via `--source`)

By default, results append to `./data/results_cache.csv` to avoid re-classifying the same repositories.
