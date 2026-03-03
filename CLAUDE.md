# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run MCP server directly
uv run finance.py

# Open MCP Inspector (interactive tool testing)
uv run mcp dev finance.py

# Install dependencies
uv sync
```

Requires Python ≥3.14 (set in `pyproject.toml`).

## Claude Desktop Integration

Add to your MCP client config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "finance": {
      "type": "stdio",
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/stock-analysis-mcp", "run", "finance.py"]
    }
  }
}
```

## Architecture

Single-file MCP server: all logic lives in `finance.py`. `main.py` is unused scaffolding.

- Uses `FastMCP` from `mcp.server.fastmcp` — each tool is a function decorated with `@mcp.tool()`
- Data source: `yfinance` only, no API keys required
- Entry point: `if __name__ == "__main__": mcp.run()`

### Tools in `finance.py`

| Function | Data source |
|----------|-------------|
| `get_stock_price` | `stock.fast_info` |
| `get_valuation_analysis` | `stock.info`, `stock.history()`, `stock.quarterly_financials` |
| `get_technical_indicators` | `stock.history(period="1y")`, `stock.info` |
| `get_fundamental_health` | `stock.info`, `stock.quarterly_financials`, `stock.cashflow` |
| `get_dividend_info` | `stock.info`, `stock.dividends` |
| `get_stock_report` | All of the above combined |

## Key Conventions

- **Taiwan stocks**: `{代號}.TW` (上市), `{代號}.TWO` (上櫃) — yfinance has sparse financial data for them
- **None checks**: All indicators must guard against missing data with fallback text (e.g. `"資料不足，無法計算"`)
- **Currency**: Always read from `stock.info.get('currency')`, never hardcode
- **Quarter labels**: Derive from timestamp with `(date.month - 1) // 3 + 1`
- **Dividends resample**: Strip timezone first — `dividends.index.tz_convert(None)` before `.resample('YE')`
- **FCF**: `Operating Cash Flow + Capital Expenditure` (capex is already negative in yfinance)
- **Current price**: `info.get('currentPrice') or info.get('regularMarketPrice')` as fallback
