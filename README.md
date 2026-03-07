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

### 方式一：Docker 本地執行

#### 1. 建構 Image

```bash
docker build -t stock-analysis-mcp .
```

#### 2. 測試 Container 是否正常啟動

```bash
docker run --rm -i -e MCP_TRANSPORT=stdio stock-analysis-mcp:latest
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
      "args": ["run", "--rm", "-i", "-e", "MCP_TRANSPORT=stdio", "stock-analysis-mcp:latest"]
    }
  }
}
```

### 方式二：Docker + ngrok 對外公開（遠端存取）

**前置需求**：Docker、[ngrok](https://ngrok.com)（需登入帳號）

#### 1. 建構 Image

```bash
docker build -t stock-analysis-mcp:latest .
```

#### 2. 啟動 HTTP 模式 Container

```bash
docker run --rm -p 8000:8000 stock-analysis-mcp:latest
```

看到以下訊息即表示成功：

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

#### 3. 開另一個 Terminal，啟動 ngrok

```bash
ngrok http 8000
```

ngrok 會顯示對外 URL，例如：

```
Forwarding  https://xxxx-xxx-xxx.ngrok-free.app -> http://localhost:8000
```

#### 4. 設定 MCP Client

在 `.mcp.json`（或 `claude_desktop_config.json`）加入，URL 結尾必須加 `/mcp`：

```json
{
  "mcpServers": {
    "stock-analysis": {
      "type": "http",
      "url": "https://xxxx-xxx-xxx.ngrok-free.app/mcp"
    }
  }
}
```

> **注意**：ngrok 免費版每次重啟 URL 都會改變，需同步更新 client config。

