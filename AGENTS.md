# AI Stock Analysis System - Agent Guidelines

This document provides guidance for AI agents working on this Korean stock analysis project.

## Build and Development Commands

### Running the Application
```bash
# Activate virtual environment (if not already active)
source /home/kimhc/Stock/venv/bin/activate

# CLI mode - Interactive stock analysis
python main.py
python main.py 삼성전er        # Analyze by name
python main.py 005930         # Analyze by stock code
python main.py -c 005930      # Analyze by direct code

# Web Dashboard (Streamlit)
streamlit run dashboard.py

# Daily Top 100 Screener
python daily_top100.py

# Full Market Screening (KOSPI + KOSDAQ)
python market_screener.py
```

### Linting and Testing
This project does NOT have formal tests or linting configured. Before committing changes:
```bash
# Syntax check
python -m py_compile <filename>.py

# Run manually test critical paths:
python main.py 005930          # Test CLI with Samsung Electronics
python -c "from technical_analyst import TechnicalAnalyst; print('OK')"
```

## Code Style Guidelines

### Import Order
Follow this order (no blank lines between sections):
1. Standard library (`os`, `sys`, `json`, `datetime`)
2. Third-party (`pandas`, `requests`, `streamlit`, `FinanceDataReader`)
3. Local modules (`from config import ...`, `from dart_analyst import ...`)

```python
# CORRECT
import os
import sys
from datetime import datetime

import pandas as pd
import requests
from dotenv import load_dotenv

from config import ScreeningConfig
from technical_analyst import TechnicalAnalyst
```

### Naming Conventions
- **Functions/Variables**: `snake_case` (`get_financials`, `stock_code`, `total_score`)
- **Classes**: `PascalCase` (`FundamentalAnalyst`, `TechnicalAnalyst`, `ScreeningConfig`)
- **Constants**: `UPPER_SNAKE_CASE` (`MIN_MARKET_CAP`, `MAX_WORKERS`, `BASE_DIR`)
- **Private methods**: Leading underscore (`_analyze_candle_patterns`)

### Error Handling
Use try/except blocks with descriptive print statements. Return None/empty dict on failure:
```python
try:
    df = fdr.DataReader(code, start_date)
    return df
except Exception as e:
    print(f"데이터 로드 실패: {e}")
    return None
```
NEVER use empty `except:` without at least logging the error.

### Configuration Management
All configurable parameters live in `config.py`:
- Use class-based structure (`class ScreeningConfig`, `class IndicatorWeights`)
- Document units and ranges in comments
- Provide helper functions for dynamic values (`get_filename()`, `get_filepath()`)

### File Structure
- `main.py` - CLI entry point, argument parsing, interactive mode
- `dashboard.py` - Streamlit web UI
- `config.py` - All configuration (weights, thresholds, paths)
- `*_analyst.py` - Analysis modules (fundamental, technical, sentiment)
- `stock_utils.py` - Shared utilities (DART code lookup, KRX listings)
- `*_screener.py` - Batch screening scripts

### Comments and Documentation
- **Language**: Korean (한국어) for comments and user-facing strings
- **Docstrings**: Use triple quotes for class/function documentation
```python
def get_ohlcv(self, stock_code, days=365):
    """
    주가 데이터 수집
    Args:
        stock_code: 종목코드 (예: "005930")
        days: 기간 (기본값 365일)
    Returns:
        DataFrame with OHLCV data
    """
```

### Type Safety
Type hints are NOT consistently used in this codebase. When adding new features:
- Optional: Add type hints for complex functions
- DO NOT suppress type errors with `# type: ignore` or `cast()`
- Use `pd.isna()` for missing data checks in pandas DataFrames

### Environment Variables
Use `python-dotenv` for configuration:
```python
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("DART_API_KEY")
```
All secrets must be in `.env` (excluded from git).

### Pandas/NumPy Patterns
- Use `df[['Code', 'Name']]` for column selection (not deprecated `df.loc[:, ...]`)
- Handle missing values: `df.dropna()`, `df.fillna()`, or `pd.notna()` checks
- Vectorized operations preferred over loops
```python
# CORRECT
df['SMA_5'] = ta.sma(df['Close'], length=5)
rsi_val = df.iloc[-1]['RSI']
if pd.isna(rsi_val): rsi_val = 50
```

### Streamlit Specifics
- Use `@st.cache_resource` for expensive objects (DART readers, analyst instances)
- Use `@st.cache_data` for data that changes infrequently
- Session state management: `if 'key' not in st.session_state: st.session_state['key'] = default`
- Always use `unique_key` in repeated UI elements: `st.button("Label", key=f"btn_{id}")`

### API Integration
- Rate-limit external API calls (DART, FinanceDataReader)
- Cache results where possible
- Handle missing API keys gracefully:
```python
api_key = os.getenv("DART_API_KEY")
if not api_key:
    print("⚠️ DART_API_KEY가 설정되지 않았습니다.")
    return None
```

## Project Context

This is an AI-powered Korean stock analysis system with three main components:
1. **Fundamental Analysis** (20%): DART API for financial data (liquidity, debt ratio, profit margin)
2. **Technical Analysis** (60%): 18+ indicators using pandas-ta (MA, RSI, MACD, ADX, candle patterns)
3. **Sentiment Analysis** (20%): Web scraping from Naver Finance (news + discussion boards)

Output formats: Excel, PDF, JSON, CSV, Markdown in `output/` directory.
