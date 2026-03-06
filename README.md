# Stock Analysis MCP Server

以 [FastMCP](https://github.com/jlowin/fastmcp) 建構的股票分析 MCP Server，資料來源為 `yfinance`，無需 API 金鑰。

## Tools

| Tool | 說明 |
|------|------|
| `get_stock_price` | 即時股價 |
| `get_valuation_analysis` | 估值分析（P/E、P/B、EV/EBITDA 等） |
| `get_technical_indicators` | 技術指標（MA、RSI、MACD 等） |
| `get_fundamental_health` | 基本面健康檢查（獲利、負債、現金流） |
| `get_dividend_info` | 股息資訊與歷年配發紀錄 |
| `get_stock_report` | 完整綜合報告 |

> 台灣股票代號格式：上市用 `{代號}.TW`，上櫃用 `{代號}.TWO`（例如 `2330.TW`）

---

## 使用方式

### 方式一：本地直接執行

**前置需求**：Python ≥ 3.14、[uv](https://github.com/astral-sh/uv)

```bash
# 安裝依賴
uv sync

# 啟動 MCP Server
uv run finance.py

# 用 MCP Inspector 互動測試
uv run mcp dev finance.py
```

### 方式二：Docker 執行（推薦）

#### 1. 建構 Image

```bash
docker build -t stock-analysis-mcp .
```

#### 2. 測試 Container 是否正常啟動

```bash
docker run --rm -i stock-analysis-mcp
```

> 啟動後會等待 stdin 輸入（MCP stdio 模式），`Ctrl+C` 結束即可。

#### 3. 設定 MCP Client

在 `.mcp.json`（或 `claude_desktop_config.json`）加入：

```json
{
  "mcpServers": {
    "stock-analysis": {
      "type": "stdio",
      "command": "docker",
      "args": ["run", "--rm", "-i", "stock-analysis-mcp:latest"]
    }
  }
}
```

#### 更新 Image

修改程式碼後重新 build 即可：

```bash
docker build -t stock-analysis-mcp .
```

---

## 本地開發設定（uv + MCP Client）

```json
{
  "mcpServers": {
    "stock-analysis": {
      "type": "stdio",
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/stock-analysis-mcp", "run", "finance.py"]
    }
  }
}
```
