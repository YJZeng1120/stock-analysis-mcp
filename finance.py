from mcp.server.fastmcp import FastMCP
import yfinance as yf
import math
import datetime
import httpx
from duckduckgo_search import DDGS

# 建立 MCP Server 實例
mcp = FastMCP("stock-analysis-mcp", stateless_http=True, json_response=True)


@mcp.tool()
def get_stock_price(ticker: str) -> str:
    """
    獲取指定股票代號的最新價格資訊。
    例如: 'AAPL', '2330.TW'
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.fast_info
        current_price = info['last_price']
        currency = info['currency']

        return f"{ticker} 目前價格為 {current_price:.2f} {currency}"
    except Exception as e:
        return f"無法獲取 {ticker} 的資訊: {str(e)}"


@mcp.tool()
def get_valuation_analysis(ticker: str) -> str:
    """
    估值分析：判斷股票目前是否被高估。
    綜合多個指標：P/E 歷史百分位、Graham Number、Price Percentile、Forward/Trailing P/E 比較、PEG Ratio。
    例如: 'AAPL', '2330.TW'
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        currency = info.get('currency', 'N/A')
        current_price = info.get('currentPrice') or info.get('regularMarketPrice')

        if not current_price:
            return f"無法獲取 {ticker} 的目前價格"

        lines = [f"=== {ticker} 估值分析 ===", f"目前價格: {current_price:.2f} {currency}", ""]

        # 1. Forward P/E vs Trailing P/E
        trailing_pe = info.get('trailingPE')
        forward_pe = info.get('forwardPE')

        lines.append("【本益比 P/E】")
        if trailing_pe:
            pe_label = "偏低" if trailing_pe < 15 else ("合理" if trailing_pe < 25 else "偏高")
            lines.append(f"  Trailing P/E: {trailing_pe:.2f} → {pe_label}")
        else:
            lines.append("  Trailing P/E: 資料不足")

        if forward_pe:
            fpe_label = "偏低" if forward_pe < 15 else ("合理" if forward_pe < 25 else "偏高")
            lines.append(f"  Forward P/E:  {forward_pe:.2f} → {fpe_label}")
            if trailing_pe and forward_pe:
                if forward_pe < trailing_pe:
                    lines.append("  → 預期獲利成長（Forward P/E 低於 Trailing P/E）")
                else:
                    lines.append("  → 預期獲利下滑（Forward P/E 高於 Trailing P/E）")
        else:
            lines.append("  Forward P/E: 資料不足")

        # 2. P/E 歷史百分位（近 5 年）
        lines.append("")
        lines.append("【P/E 歷史百分位（近 5 年）】")
        try:
            hist = stock.history(period="5y")
            q_financials = stock.quarterly_financials

            if not hist.empty and q_financials is not None and not q_financials.empty:
                eps_row = None
                for row_name in ['Diluted EPS', 'Basic EPS']:
                    if row_name in q_financials.index:
                        eps_row = q_financials.loc[row_name]
                        break

                if eps_row is not None and len(eps_row) >= 4:
                    ttm_eps = eps_row.iloc[:4].sum()
                    if ttm_eps and ttm_eps > 0:
                        monthly_prices = hist['Close'].resample('ME').last()
                        hist_pe_values = monthly_prices / ttm_eps
                        hist_pe_values = hist_pe_values[hist_pe_values > 0]

                        if len(hist_pe_values) > 0:
                            hist_pe = current_price / ttm_eps
                            sorted_pe = sorted(hist_pe_values)
                            percentile = sum(1 for p in sorted_pe if p <= hist_pe) / len(sorted_pe) * 100
                            min_pe = min(sorted_pe)
                            max_pe = max(sorted_pe)
                            pe_hist_label = "偏低" if percentile < 30 else ("合理" if percentile < 70 else "偏高")

                            lines.append(f"  目前 P/E (TTM): {hist_pe:.2f}")
                            lines.append(f"  5年 P/E 區間: {min_pe:.1f} ~ {max_pe:.1f}")
                            lines.append(f"  歷史百分位: {percentile:.1f}% → {pe_hist_label}")
                    else:
                        lines.append("  EPS 為負或零，無法計算歷史 P/E 百分位")
                else:
                    lines.append("  季度 EPS 資料不足，無法計算歷史百分位")
            else:
                lines.append("  歷史資料不足，無法計算")
        except Exception as e:
            lines.append(f"  計算失敗: {str(e)}")

        # 3. 股價歷史百分位（近 3/5 年）
        lines.append("")
        lines.append("【股價歷史百分位】")
        try:
            hist_5y = stock.history(period="5y")
            hist_3y = stock.history(period="3y")

            if not hist_5y.empty:
                low_5y = hist_5y['Low'].min()
                high_5y = hist_5y['High'].max()
                pct_5y = (current_price - low_5y) / (high_5y - low_5y) * 100 if high_5y > low_5y else 50
                lines.append(f"  近5年區間: {low_5y:.2f} ~ {high_5y:.2f} {currency}")
                lines.append(f"  近5年百分位: {pct_5y:.1f}%")

            if not hist_3y.empty:
                low_3y = hist_3y['Low'].min()
                high_3y = hist_3y['High'].max()
                pct_3y = (current_price - low_3y) / (high_3y - low_3y) * 100 if high_3y > low_3y else 50
                price_label = "偏低" if pct_3y < 30 else ("合理" if pct_3y < 70 else "偏高")
                lines.append(f"  近3年區間: {low_3y:.2f} ~ {high_3y:.2f} {currency}")
                lines.append(f"  近3年百分位: {pct_3y:.1f}% → 目前價格相對近3年: {price_label}")
        except Exception as e:
            lines.append(f"  計算失敗: {str(e)}")

        # 4. Graham Number
        lines.append("")
        lines.append("【Graham Number（葛拉漢內在價值）】")
        try:
            eps = info.get('trailingEps')
            bvps = info.get('bookValue')

            if eps and bvps and eps > 0 and bvps > 0:
                graham = math.sqrt(22.5 * eps * bvps)
                ratio = current_price / graham
                if ratio < 0.8:
                    graham_label = "明顯低估"
                elif ratio < 1.0:
                    graham_label = "低估"
                elif ratio < 1.2:
                    graham_label = "合理"
                else:
                    graham_label = "偏高估"

                lines.append(f"  EPS: {eps:.2f} {currency}")
                lines.append(f"  每股淨值 (BVPS): {bvps:.2f} {currency}")
                lines.append(f"  Graham Number: {graham:.2f} {currency}")
                lines.append(f"  現價/Graham: {ratio:.2f}x → {graham_label}")
            elif eps is not None and eps <= 0:
                lines.append("  EPS 為負，無法計算 Graham Number")
            else:
                lines.append("  EPS 或 BVPS 資料不足，無法計算")
        except Exception as e:
            lines.append(f"  計算失敗: {str(e)}")

        # 5. PEG Ratio
        lines.append("")
        lines.append("【PEG Ratio】")
        peg = info.get('pegRatio')
        if peg is not None:
            if peg < 0:
                peg_label = "負值（盈餘下滑）"
            elif peg < 1:
                peg_label = "偏低（成長股折價）"
            elif peg < 1.5:
                peg_label = "合理"
            else:
                peg_label = "偏高"
            lines.append(f"  PEG Ratio: {peg:.2f} → {peg_label}")
        else:
            lines.append("  資料不足，無法計算")

        return "\n".join(lines)
    except Exception as e:
        return f"無法分析 {ticker} 的估值: {str(e)}"


@mcp.tool()
def get_technical_indicators(ticker: str) -> str:
    """
    技術指標分析：MA50/MA200（均線）、RSI(14)、52週高低點。
    例如: 'AAPL', '2330.TW'
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        currency = info.get('currency', 'N/A')

        hist = stock.history(period="1y")
        if hist.empty:
            return f"無法獲取 {ticker} 的歷史資料"

        close = hist['Close']
        current_price = close.iloc[-1]

        lines = [f"=== {ticker} 技術指標分析 ===", f"目前價格: {current_price:.2f} {currency}", ""]

        # 1. MA50 / MA200 及交叉訊號
        lines.append("【均線分析】")
        ma50 = ma200 = None

        if len(close) >= 50:
            ma50 = close.rolling(50).mean().iloc[-1]
            ma50_diff = (current_price - ma50) / ma50 * 100
            ma50_dir = "↑ 在均線之上" if current_price > ma50 else "↓ 在均線之下"
            lines.append(f"  MA50:  {ma50:.2f} {currency} ({ma50_diff:+.1f}%) {ma50_dir}")
        else:
            lines.append("  MA50: 資料不足（需至少 50 天）")

        if len(close) >= 200:
            ma200 = close.rolling(200).mean().iloc[-1]
            ma200_diff = (current_price - ma200) / ma200 * 100
            ma200_dir = "↑ 在均線之上" if current_price > ma200 else "↓ 在均線之下"
            lines.append(f"  MA200: {ma200:.2f} {currency} ({ma200_diff:+.1f}%) {ma200_dir}")
        else:
            lines.append("  MA200: 資料不足（需至少 200 天）")

        if ma50 is not None and ma200 is not None:
            ma50_series = close.rolling(50).mean()
            ma200_series = close.rolling(200).mean()
            cross_signal = ""
            for i in range(len(ma50_series) - 1, max(1, len(ma50_series) - 60), -1):
                if (ma50_series.iloc[i] > ma200_series.iloc[i] and
                        ma50_series.iloc[i - 1] <= ma200_series.iloc[i - 1]):
                    days_ago = len(ma50_series) - 1 - i
                    cross_signal = f"  → 近期出現黃金交叉（{days_ago} 天前）✓ 看多訊號"
                    break
                elif (ma50_series.iloc[i] < ma200_series.iloc[i] and
                      ma50_series.iloc[i - 1] >= ma200_series.iloc[i - 1]):
                    days_ago = len(ma50_series) - 1 - i
                    cross_signal = f"  → 近期出現死亡交叉（{days_ago} 天前）✗ 看空訊號"
                    break

            if cross_signal:
                lines.append(cross_signal)
            else:
                state = "多頭排列（MA50 > MA200）" if ma50 > ma200 else "空頭排列（MA50 < MA200）"
                lines.append(f"  → {state}")

        # 2. RSI(14)
        lines.append("")
        lines.append("【RSI(14)】")
        if len(close) >= 15:
            delta = close.diff()
            avg_gain = delta.clip(lower=0).rolling(14).mean().iloc[-1]
            avg_loss = (-delta.clip(upper=0)).rolling(14).mean().iloc[-1]

            if avg_loss == 0:
                rsi = 100.0
            else:
                rsi = 100 - (100 / (1 + avg_gain / avg_loss))

            if rsi < 30:
                rsi_label = "超賣 ↑ 潛在買點"
            elif rsi > 70:
                rsi_label = "超買 ↓ 注意回調"
            else:
                rsi_label = "中性區間"
            lines.append(f"  RSI(14): {rsi:.1f} → {rsi_label}")
        else:
            lines.append("  資料不足，無法計算")

        # 3. 52週高低點
        lines.append("")
        lines.append("【52週高低點】")
        week52_high = info.get('fiftyTwoWeekHigh')
        week52_low = info.get('fiftyTwoWeekLow')

        if week52_high and week52_low:
            from_high = (current_price - week52_high) / week52_high * 100
            from_low = (current_price - week52_low) / week52_low * 100
            position_pct = (current_price - week52_low) / (week52_high - week52_low) * 100
            lines.append(f"  52週高點: {week52_high:.2f} {currency} (距高點 {from_high:.1f}%)")
            lines.append(f"  52週低點: {week52_low:.2f} {currency} (距低點 +{from_low:.1f}%)")
            lines.append(f"  在52週區間的位置: {position_pct:.1f}%")
        else:
            lines.append("  資料不足")

        return "\n".join(lines)
    except Exception as e:
        return f"無法分析 {ticker} 的技術指標: {str(e)}"


@mcp.tool()
def get_fundamental_health(ticker: str) -> str:
    """
    基本面健康度分析：營收成長、EPS 趨勢、毛利率、負債比率、自由現金流。
    例如: 'AAPL', '2330.TW'
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        currency = info.get('currency', 'N/A')

        lines = [f"=== {ticker} 基本面健康度 ===", ""]

        # 取一次季度財報
        q_financials = stock.quarterly_financials

        # 1. 近 4 季營收成長率（YoY）
        lines.append("【季度營收成長率 (YoY)】")
        try:
            if q_financials is not None and not q_financials.empty:
                revenue_row = None
                for row_name in ['Total Revenue', 'Revenue']:
                    if row_name in q_financials.index:
                        revenue_row = q_financials.loc[row_name]
                        break

                if revenue_row is not None and len(revenue_row) >= 5:
                    cols = revenue_row.index.sort_values(ascending=False)
                    revenue_sorted = revenue_row[cols]

                    for i in range(min(4, len(cols))):
                        if i + 4 < len(cols):
                            curr_q = revenue_sorted.iloc[i]
                            prev_q = revenue_sorted.iloc[i + 4]
                            if prev_q and prev_q != 0 and curr_q is not None:
                                yoy = (curr_q - prev_q) / abs(prev_q) * 100
                                date = cols[i]
                                quarter = (date.month - 1) // 3 + 1
                                qlabel = f"{date.year} Q{quarter}"
                                trend = "▲" if yoy > 0 else "▼"
                                lines.append(f"  {qlabel}: {trend} {yoy:+.1f}%")
                else:
                    lines.append("  季度財報資料不足（需至少 5 季資料）")
            else:
                lines.append("  無法取得季度財報")
        except Exception as e:
            lines.append(f"  計算失敗: {str(e)}")

        # 2. EPS 成長趨勢（近 4 季）
        lines.append("")
        lines.append("【EPS 成長趨勢（近 4 季）】")
        try:
            if q_financials is not None and not q_financials.empty:
                eps_row = None
                for row_name in ['Diluted EPS', 'Basic EPS']:
                    if row_name in q_financials.index:
                        eps_row = q_financials.loc[row_name]
                        break

                if eps_row is not None and len(eps_row) >= 4:
                    cols = eps_row.index.sort_values(ascending=False)
                    eps_sorted = eps_row[cols]
                    eps_values = []
                    for i in range(min(4, len(cols))):
                        date = cols[i]
                        quarter = (date.month - 1) // 3 + 1
                        qlabel = f"{date.year} Q{quarter}"
                        val = eps_sorted.iloc[i]
                        eps_values.append(val)
                        lines.append(f"  {qlabel}: {val:.2f} {currency}")

                    if len(eps_values) >= 2:
                        if eps_values[0] > eps_values[-1]:
                            lines.append("  → EPS 呈成長趨勢 ▲")
                        elif eps_values[0] < eps_values[-1]:
                            lines.append("  → EPS 呈下滑趨勢 ▼")
                        else:
                            lines.append("  → EPS 持平")
                else:
                    lines.append("  季度 EPS 資料不足")
            else:
                lines.append("  無法取得季度財報")
        except Exception as e:
            lines.append(f"  計算失敗: {str(e)}")

        # 3. 毛利率、營業利益率、淨利率
        lines.append("")
        lines.append("【獲利能力】")
        gross_margin = info.get('grossMargins')
        operating_margin = info.get('operatingMargins')
        profit_margin = info.get('profitMargins')

        if gross_margin is not None:
            gm_pct = gross_margin * 100
            gm_label = "優秀" if gm_pct >= 40 else ("良好" if gm_pct >= 20 else "偏低")
            lines.append(f"  毛利率: {gm_pct:.1f}% → {gm_label}")
        else:
            lines.append("  毛利率: 資料不足")

        if operating_margin is not None:
            om_pct = operating_margin * 100
            om_label = "優秀" if om_pct >= 15 else ("良好" if om_pct >= 5 else "偏低")
            lines.append(f"  營業利益率: {om_pct:.1f}% → {om_label}")
        else:
            lines.append("  營業利益率: 資料不足")

        if profit_margin is not None:
            lines.append(f"  淨利率: {profit_margin * 100:.1f}%")

        # 4. 財務槓桿
        lines.append("")
        lines.append("【財務槓桿】")
        debt_to_equity = info.get('debtToEquity')
        if debt_to_equity is not None:
            de_label = "低槓桿（財務穩健）" if debt_to_equity < 50 else ("中等槓桿" if debt_to_equity < 100 else "高槓桿（需注意）")
            lines.append(f"  負債/股東權益 (D/E): {debt_to_equity:.1f}% → {de_label}")
        else:
            lines.append("  D/E 比率: 資料不足")

        current_ratio = info.get('currentRatio')
        if current_ratio is not None:
            cr_label = "流動性佳" if current_ratio >= 2 else ("尚可" if current_ratio >= 1 else "流動性偏緊")
            lines.append(f"  流動比率: {current_ratio:.2f} → {cr_label}")

        # 5. 自由現金流量
        lines.append("")
        lines.append("【自由現金流量】")
        try:
            cashflow = stock.cashflow
            if cashflow is not None and not cashflow.empty:
                ocf = None
                for rn in ['Operating Cash Flow', 'Total Cash From Operating Activities']:
                    if rn in cashflow.index:
                        ocf = cashflow.loc[rn].iloc[0]
                        break

                capex = None
                for rn in ['Capital Expenditure', 'Capital Expenditures']:
                    if rn in cashflow.index:
                        capex = cashflow.loc[rn].iloc[0]
                        break

                if ocf is not None:
                    fcf = ocf + capex if capex is not None else ocf
                    fcf_label = "正值 ✓（自由現金流健康）" if fcf > 0 else "負值 ✗（需注意）"

                    def fmt_amount(v):
                        if abs(v) >= 1e9:
                            return f"{v / 1e9:.2f}B"
                        elif abs(v) >= 1e6:
                            return f"{v / 1e6:.2f}M"
                        return f"{v:.0f}"

                    lines.append(f"  營業現金流: {fmt_amount(ocf)} {currency}")
                    if capex is not None:
                        lines.append(f"  資本支出: {fmt_amount(capex)} {currency}")
                    lines.append(f"  自由現金流: {fmt_amount(fcf)} {currency} → {fcf_label}")
                else:
                    lines.append("  現金流資料不足")
            else:
                lines.append("  無法取得現金流量表")
        except Exception as e:
            lines.append(f"  計算失敗: {str(e)}")

        return "\n".join(lines)
    except Exception as e:
        return f"無法分析 {ticker} 的基本面: {str(e)}"


@mcp.tool()
def get_dividend_info(ticker: str) -> str:
    """
    股息分析：殖利率、配息率、近 5 年配息歷史與成長趨勢。
    例如: 'AAPL', '2330.TW'
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        currency = info.get('currency', 'N/A')
        name = info.get('longName', ticker)

        lines = [f"=== {ticker} ({name}) 股息分析 ===", ""]

        # 1. 殖利率
        dividend_yield = info.get('dividendYield')
        if dividend_yield:
            yield_pct = dividend_yield * 100
            yield_label = "高殖利率" if yield_pct >= 4 else ("中等殖利率" if yield_pct >= 2 else "低殖利率")
            lines.append(f"殖利率: {yield_pct:.2f}% → {yield_label}")
        else:
            lines.append("殖利率: 目前無配息或資料不足")

        # 2. 配息率
        payout_ratio = info.get('payoutRatio')
        if payout_ratio:
            pr_pct = payout_ratio * 100
            if pr_pct > 100:
                pr_label = "超過盈餘（不可持續）"
            elif pr_pct >= 70:
                pr_label = "偏高（需注意持續性）"
            elif pr_pct >= 30:
                pr_label = "合理"
            else:
                pr_label = "保守（有成長空間）"
            lines.append(f"配息率 (Payout Ratio): {pr_pct:.1f}% → {pr_label}")
        else:
            lines.append("配息率: 資料不足")

        annual_dividend = info.get('dividendRate')
        if annual_dividend:
            lines.append(f"年化股息: {annual_dividend:.2f} {currency}/股")

        # 3. 近 5 年配息歷史（年度）
        lines.append("")
        lines.append("【近 5 年配息歷史（年度）】")
        try:
            dividends = stock.dividends
            if dividends is not None and not dividends.empty:
                # 去除時區資訊再 resample
                if dividends.index.tz is not None:
                    dividends.index = dividends.index.tz_convert(None)
                annual_div = dividends.resample('YE').sum()
                recent_5y = annual_div.tail(5)

                if len(recent_5y) > 0:
                    for date, amount in recent_5y.items():
                        lines.append(f"  {date.year}: {amount:.2f} {currency}")

                    if len(recent_5y) >= 2:
                        first_div = recent_5y.iloc[0]
                        last_div = recent_5y.iloc[-1]

                        if first_div > 0:
                            growth = (last_div - first_div) / first_div * 100
                            cagr_years = len(recent_5y) - 1
                            cagr = ((last_div / first_div) ** (1 / cagr_years) - 1) * 100 if cagr_years > 0 else 0

                            if cagr > 5:
                                div_trend = "穩定成長 ▲"
                            elif cagr > 0:
                                div_trend = "緩步成長 →"
                            elif cagr == 0:
                                div_trend = "持平 —"
                            else:
                                div_trend = "下滑 ▼"

                            lines.append(f"  5年累計成長: {growth:+.1f}%")
                            lines.append(f"  年化成長率 (CAGR): {cagr:.1f}% → {div_trend}")
                else:
                    lines.append("  近 5 年無配息記錄")
            else:
                lines.append("  無配息歷史資料")
        except Exception as e:
            lines.append(f"  計算失敗: {str(e)}")

        return "\n".join(lines)
    except Exception as e:
        return f"無法分析 {ticker} 的股息: {str(e)}"


@mcp.tool()
def get_earnings_call_summary(ticker: str) -> str:
    """
    法說會 / 財報電話會議摘要：整合最新 EPS 達標歷史、分析師共識預估、
    目標價、評等異動，以及網路搜尋到的法說會 / 財報重點。
    適用於美股（如 'AAPL'）及台股（如 '2330.TW'）。
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        currency = info.get('currency', 'N/A')
        name = info.get('longName', ticker)
        current_price = info.get('currentPrice') or info.get('regularMarketPrice')

        lines = [f"=== {ticker} ({name}) 法說會 / 財報摘要 ===", ""]

        # 區塊 1：下次財報日
        lines.append("【下次財報日】")
        try:
            ts = info.get('earningsTimestampStart') or info.get('earningsTimestamp')
            if ts:
                dt = datetime.datetime.fromtimestamp(ts)
                lines.append(f"  預計: {dt.strftime('%Y-%m-%d')}")
            else:
                lines.append("  資料不足")
        except Exception:
            lines.append("  資料不足")

        # 區塊 2：近期 EPS 達標歷史（8 季）
        lines.append("")
        lines.append("【近期 EPS 達標歷史（最近 8 季）】")
        try:
            eh = stock.earnings_history
            if eh is not None and not eh.empty:
                recent = eh.tail(8)
                beat_count = 0
                total_count = 0
                for date, row in recent.iterrows():
                    actual = row.get('epsActual')
                    estimate = row.get('epsEstimate')
                    surprise = row.get('surprisePercent')
                    if actual is None or estimate is None:
                        continue
                    total_count += 1
                    surprise_pct = surprise * 100 if surprise is not None else None
                    beat = actual >= estimate
                    if beat:
                        beat_count += 1
                    beat_label = "✓ 達標" if beat else "✗ 未達"
                    surprise_str = f" ({surprise_pct:+.1f}%)" if surprise_pct is not None else ""
                    try:
                        date_str = date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else str(date)[:10]
                    except Exception:
                        date_str = str(date)[:10]
                    lines.append(f"  {date_str}: 實際 {actual:.2f} vs 預估 {estimate:.2f}{surprise_str} {beat_label}")
                if total_count > 0:
                    beat_rate = beat_count / total_count * 100
                    lines.append(f"  → 達標率: {beat_count}/{total_count} ({beat_rate:.0f}%)")
            else:
                lines.append("  資料不足")
        except Exception as e:
            lines.append(f"  資料不足: {str(e)}")

        # 區塊 3：分析師共識預估（EPS + 營收）
        lines.append("")
        lines.append("【分析師共識預估】")
        try:
            ee = stock.earnings_estimate
            if ee is not None and not ee.empty:
                lines.append("  EPS 預估:")
                label_map = {'0q': '本季', '+1q': '下季', '0y': '本年', '+1y': '明年'}
                for period in ['0q', '+1q', '0y', '+1y']:
                    if period in ee.index:
                        row = ee.loc[period]
                        avg = row.get('avg')
                        growth = row.get('growth')
                        n = row.get('numberOfAnalysts')
                        if avg is not None:
                            growth_str = f", YoY {growth * 100:+.1f}%" if growth is not None else ""
                            n_str = f", {int(n)} 位分析師" if n is not None else ""
                            lines.append(f"    {label_map.get(period, period)}: {avg:.2f} {currency}{growth_str}{n_str}")
            else:
                lines.append("  EPS 預估: 資料不足")
        except Exception as e:
            lines.append(f"  EPS 預估資料不足: {str(e)}")

        try:
            re = stock.revenue_estimate
            if re is not None and not re.empty:
                lines.append("  營收預估:")
                label_map = {'0q': '本季', '+1q': '下季', '0y': '本年', '+1y': '明年'}
                for period in ['0q', '+1q', '0y', '+1y']:
                    if period in re.index:
                        row = re.loc[period]
                        avg = row.get('avg')
                        growth = row.get('growth')
                        n = row.get('numberOfAnalysts')
                        if avg is not None:
                            if abs(avg) >= 1e9:
                                avg_str = f"{avg / 1e9:.2f}B"
                            elif abs(avg) >= 1e6:
                                avg_str = f"{avg / 1e6:.2f}M"
                            else:
                                avg_str = f"{avg:.0f}"
                            growth_str = f", YoY {growth * 100:+.1f}%" if growth is not None else ""
                            n_str = f", {int(n)} 位分析師" if n is not None else ""
                            lines.append(f"    {label_map.get(period, period)}: {avg_str} {currency}{growth_str}{n_str}")
        except Exception as e:
            lines.append(f"  營收預估資料不足: {str(e)}")

        # 區塊 4：分析師目標價
        lines.append("")
        lines.append("【分析師目標價】")
        try:
            apt = stock.analyst_price_targets
            if apt is not None:
                mean_target = apt.get('mean')
                high_target = apt.get('high')
                low_target = apt.get('low')
                if mean_target:
                    lines.append(f"  共識目標價: {mean_target:.2f} {currency}")
                if high_target:
                    lines.append(f"  樂觀目標價: {high_target:.2f} {currency}")
                if low_target:
                    lines.append(f"  保守目標價: {low_target:.2f} {currency}")
                if mean_target and current_price:
                    upside = (mean_target - current_price) / current_price * 100
                    upside_label = "潛在上漲空間" if upside > 0 else "潛在下跌空間"
                    lines.append(f"  現價 → 共識目標: {upside:+.1f}% ({upside_label})")
            else:
                lines.append("  資料不足")
        except Exception as e:
            lines.append(f"  資料不足: {str(e)}")

        # 區塊 5：近 90 天分析師評等異動
        lines.append("")
        lines.append("【近 90 天分析師評等異動】")
        try:
            ud = stock.upgrades_downgrades
            if ud is not None and not ud.empty:
                cutoff = datetime.datetime.now() - datetime.timedelta(days=90)
                # index is GradeDate
                if hasattr(ud.index, 'tz_convert'):
                    ud.index = ud.index.tz_convert(None)
                elif hasattr(ud.index, 'tz_localize'):
                    ud.index = ud.index.tz_localize(None)
                recent_ud = ud[ud.index >= cutoff]
                if not recent_ud.empty:
                    for date, row in recent_ud.iterrows():
                        firm = row.get('Firm', 'N/A')
                        action = row.get('Action', '')
                        to_grade = row.get('ToGrade', '')
                        from_grade = row.get('FromGrade', '')
                        try:
                            date_str = date.strftime('%Y-%m-%d')
                        except Exception:
                            date_str = str(date)[:10]
                        if from_grade:
                            lines.append(f"  {date_str} [{firm}] {action}: {from_grade} → {to_grade}")
                        else:
                            lines.append(f"  {date_str} [{firm}] {action}: {to_grade}")
                else:
                    lines.append("  近 90 天無評等異動記錄（台股此資料通常為空）")
            else:
                lines.append("  無評等異動資料（台股此資料通常為空）")
        except Exception as e:
            lines.append(f"  資料不足: {str(e)}")

        # 區塊 6：DuckDuckGo 搜尋結果
        lines.append("")
        lines.append("【網路搜尋：法說會 / 財報重點】")
        try:
            year = datetime.datetime.now().year
            is_taiwan = ticker.upper().endswith('.TW') or ticker.upper().endswith('.TWO')
            ticker_base = ticker.split('.')[0]

            queries = []
            if is_taiwan:
                queries = [
                    f"{ticker_base} 法說會 {year}",
                    f"{name} earnings call {year}",
                    f"{ticker_base} 財報 法人說明會 {year}",
                ]
            else:
                queries = [
                    f'"{name}" earnings call highlights {year}',
                    f'"{ticker}" earnings call transcript {year}',
                ]

            seen_urls = set()
            results = []
            ddgs = DDGS()
            for query in queries:
                try:
                    hits = ddgs.text(query, max_results=5)
                    for hit in hits:
                        url = hit.get('href', '')
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            results.append(hit)
                        if len(results) >= 8:
                            break
                except Exception:
                    continue
                if len(results) >= 8:
                    break

            if results:
                for i, r in enumerate(results[:8], 1):
                    title = r.get('title', '無標題')
                    url = r.get('href', '')
                    body = r.get('body', '')
                    if len(body) > 300:
                        body = body[:300] + "..."
                    lines.append(f"  {i}. {title}")
                    lines.append(f"     {url}")
                    if body:
                        lines.append(f"     {body}")
            else:
                lines.append("  未找到相關搜尋結果")
        except Exception as e:
            lines.append(f"  搜尋失敗（網路問題或服務不可用）: {str(e)}")

        return "\n".join(lines)
    except Exception as e:
        return f"無法取得 {ticker} 的法說會摘要: {str(e)}"


@mcp.tool()
def get_institutional_trading(ticker: str) -> str:
    """
    機構法人買賣超與持股概況。
    台股 (.TW/.TWO)：三大法人（外資、投信、自營商）近 5 日買賣超明細與趨勢。
    美股：機構法人持股比例、前十大機構股東、前五大共同基金。
    例如: 'AAPL', '2330.TW', '6667.TWO'
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        name = info.get('longName', ticker)
        is_tw = ticker.upper().endswith('.TW')
        is_two = ticker.upper().endswith('.TWO')
        is_taiwan = is_tw or is_two
        ticker_base = ticker.split('.')[0]

        lines = [f"=== {ticker} ({name}) 機構法人持股概況 ===", ""]

        if is_taiwan:
            # 區塊 1：主要持股概況（yfinance）
            lines.append("【主要持股概況（yfinance）】")
            try:
                mh = stock.major_holders
                if mh is not None and not mh.empty:
                    def get_mh_value(key):
                        if key in mh.index:
                            return mh.loc[key].iloc[0]
                        return None

                    inst_pct = get_mh_value('institutionsPercentHeld')
                    insider_pct = get_mh_value('insidersPercentHeld')
                    inst_count = get_mh_value('institutionsCount')

                    if inst_pct is not None:
                        lines.append(f"  機構整體持股: {float(inst_pct) * 100:.2f}%")
                    if insider_pct is not None:
                        lines.append(f"  內部人持股: {float(insider_pct) * 100:.2f}%")
                    if inst_count is not None:
                        lines.append(f"  機構家數: {int(float(inst_count))}")
                else:
                    lines.append("  資料不足")
            except Exception:
                lines.append("  資料不足")
            lines.append("  ※ 大戶持股比（400張以上）請參考集保所持股分散表，無免費 API")

            # 區塊 2：三大法人近 5 日買賣超
            lines.append("")
            lines.append("【三大法人近 5 日買賣超】")
            try:
                def get_recent_weekdays(n=15):
                    days = []
                    d = datetime.date.today()
                    while len(days) < n:
                        if d.weekday() < 5:
                            days.append(d)
                        d -= datetime.timedelta(days=1)
                    return days

                recent_dates = get_recent_weekdays(15)
                trading_data = []

                if is_tw:
                    for d in recent_dates:
                        if len(trading_data) >= 5:
                            break
                        date_str = d.strftime('%Y%m%d')
                        url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}&selectType=ALL"
                        try:
                            resp = httpx.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
                            data = resp.json()
                            if data.get('stat') != 'OK':
                                continue
                            fields = data.get('fields', [])
                            rows = data.get('data', [])

                            def find_field_idx(keywords):
                                for i, f in enumerate(fields):
                                    if all(k in f for k in keywords):
                                        return i
                                return None

                            foreign_idx = find_field_idx(['外資及陸資', '買賣超'])
                            trust_idx = find_field_idx(['投信', '買賣超'])
                            dealer_idx = find_field_idx(['自營商(自行買賣)', '買賣超'])
                            total_idx = find_field_idx(['三大法人', '買賣超'])
                            if total_idx is None:
                                total_idx = find_field_idx(['三大法人'])

                            if None in (foreign_idx, trust_idx, dealer_idx):
                                continue

                            found_row = None
                            for row in rows:
                                if row and row[0] == ticker_base:
                                    found_row = row
                                    break
                            if found_row is None:
                                continue

                            def parse_val(v):
                                v = str(v).strip()
                                if not v or v == '-':
                                    return None
                                return int(v.replace(',', ''))

                            foreign = parse_val(found_row[foreign_idx]) if foreign_idx < len(found_row) else None
                            trust = parse_val(found_row[trust_idx]) if trust_idx < len(found_row) else None
                            dealer = parse_val(found_row[dealer_idx]) if dealer_idx < len(found_row) else None
                            total = parse_val(found_row[total_idx]) if total_idx is not None and total_idx < len(found_row) else None

                            if None in (foreign, trust, dealer):
                                continue
                            if total is None:
                                total = foreign + trust + dealer

                            trading_data.append((d.strftime('%Y-%m-%d'), foreign, trust, dealer, total))
                        except Exception:
                            continue
                else:
                    # TPEX OpenAPI (.TWO)
                    for d in recent_dates:
                        if len(trading_data) >= 5:
                            break
                        date_str = d.strftime('%Y/%m/%d')
                        url = f"https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading?date={date_str}"
                        try:
                            resp = httpx.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
                            data = resp.json()
                            if not isinstance(data, list):
                                continue

                            found_row = None
                            for item in data:
                                if item.get('Code') == ticker_base:
                                    found_row = item
                                    break
                            if found_row is None:
                                continue

                            def parse_tpex_val(v):
                                if v is None:
                                    return None
                                v = str(v).strip()
                                if not v or v == '-':
                                    return None
                                return int(v.replace(',', ''))

                            foreign = parse_tpex_val(found_row.get('Foreign_Investor_Net'))
                            trust = parse_tpex_val(found_row.get('Investment_Trust_Net'))
                            dealer = parse_tpex_val(found_row.get('Dealer_Net'))
                            total = parse_tpex_val(found_row.get('Total_Net'))

                            if None in (foreign, trust, dealer):
                                continue
                            if total is None:
                                total = foreign + trust + dealer

                            trading_data.append((d.strftime('%Y-%m-%d'), foreign, trust, dealer, total))
                        except Exception:
                            continue

                if trading_data:
                    lines.append(f"  {'日期':<12} {'外資':>12} {'投信':>10} {'自營商':>10} {'三大法人合計':>14}")
                    lines.append("  " + "-" * 62)

                    def fmt_val(v):
                        sign = '+' if v >= 0 else ''
                        return f"{sign}{v:,}"

                    sum_foreign = sum_trust = sum_dealer = sum_total = 0
                    for date_str, foreign, trust, dealer, total in trading_data:
                        lines.append(f"  {date_str:<12} {fmt_val(foreign):>12} {fmt_val(trust):>10} {fmt_val(dealer):>10} {fmt_val(total):>14}")
                        sum_foreign += foreign
                        sum_trust += trust
                        sum_dealer += dealer
                        sum_total += total

                    lines.append("  " + "-" * 62)
                    lines.append(f"  5日累計：外資 {fmt_val(sum_foreign)} | 投信 {fmt_val(sum_trust)} | 自營 {fmt_val(sum_dealer)} | 合計 {fmt_val(sum_total)}")

                    totals = [row[4] for row in trading_data]
                    if all(t > 0 for t in totals):
                        trend = f"法人連買 {len(totals)} 日"
                    elif all(t < 0 for t in totals):
                        trend = f"法人連賣 {len(totals)} 日"
                    else:
                        buy_days = sum(1 for t in totals if t > 0)
                        sell_days = sum(1 for t in totals if t < 0)
                        trend = f"混合（買超 {buy_days} 日 / 賣超 {sell_days} 日）"
                    lines.append(f"  趨勢：{trend}")
                else:
                    lines.append("  近期無三大法人買賣超資料（可能因假日或 API 暫時無法取得）")
            except Exception as e:
                lines.append(f"  三大法人資料取得失敗: {str(e)}")

            # 區塊 3：外資持股比補充
            lines.append("")
            lines.append("【外資持股比（yfinance）】")
            try:
                held_pct = info.get('heldPercentInstitutions')
                if held_pct is not None:
                    lines.append(f"  機構/外資持股比: {held_pct * 100:.2f}%")
                else:
                    lines.append("  資料不足")
            except Exception:
                lines.append("  資料不足")

        else:
            # 【美股路徑】

            # 區塊 1：主要持股比例
            lines.append("【主要持股比例】")
            try:
                mh = stock.major_holders
                if mh is not None and not mh.empty:
                    def get_mh_value(key):
                        if key in mh.index:
                            return mh.loc[key].iloc[0]
                        return None

                    inst_pct = get_mh_value('institutionsPercentHeld')
                    insider_pct = get_mh_value('insidersPercentHeld')
                    inst_float_pct = get_mh_value('institutionsFloatPercentHeld')
                    inst_count = get_mh_value('institutionsCount')

                    if inst_pct is not None:
                        lines.append(f"  機構持股: {float(inst_pct) * 100:.2f}%")
                    if insider_pct is not None:
                        lines.append(f"  內部人持股: {float(insider_pct) * 100:.2f}%")
                    if inst_float_pct is not None:
                        lines.append(f"  機構持浮動股比: {float(inst_float_pct) * 100:.2f}%")
                    if inst_count is not None:
                        lines.append(f"  機構家數: {int(float(inst_count))}")
                else:
                    lines.append("  資料不足")
            except Exception:
                lines.append("  資料不足")

            # 區塊 2：前十大機構股東
            lines.append("")
            lines.append("【前十大機構股東】")
            try:
                ih = stock.institutional_holders
                if ih is not None and not ih.empty:
                    if 'pctHeld' in ih.columns:
                        ih = ih.sort_values('pctHeld', ascending=False)
                    top10 = ih.head(10)
                    for _, row in top10.iterrows():
                        holder = row.get('Holder', 'N/A')
                        pct = row.get('pctHeld')
                        shares = row.get('Shares')
                        pct_change = row.get('pctChange')

                        pct_str = f"{float(pct) * 100:.2f}%" if pct is not None else "N/A"
                        shares_str = ""
                        if shares is not None:
                            s = float(shares)
                            if abs(s) >= 1e9:
                                shares_str = f" ({s/1e9:.2f}B 股)"
                            elif abs(s) >= 1e6:
                                shares_str = f" ({s/1e6:.2f}M 股)"
                            else:
                                shares_str = f" ({int(s):,} 股)"
                        change_str = ""
                        if pct_change is not None:
                            chg = float(pct_change) * 100
                            arrow = "▲" if chg > 0 else ("▼" if chg < 0 else "—")
                            change_str = f" {arrow}{abs(chg):.1f}%"
                        lines.append(f"  {holder}: {pct_str}{shares_str}{change_str}")
                else:
                    lines.append("  資料不足")
            except Exception as e:
                lines.append(f"  資料不足: {str(e)}")

            # 區塊 3：前五大共同基金
            lines.append("")
            lines.append("【前五大共同基金】")
            try:
                mfh = stock.mutualfund_holders
                if mfh is not None and not mfh.empty:
                    if 'pctHeld' in mfh.columns:
                        mfh = mfh.sort_values('pctHeld', ascending=False)
                    top5 = mfh.head(5)
                    for _, row in top5.iterrows():
                        holder = row.get('Holder', 'N/A')
                        pct = row.get('pctHeld')
                        shares = row.get('Shares')
                        pct_change = row.get('pctChange')

                        pct_str = f"{float(pct) * 100:.2f}%" if pct is not None else "N/A"
                        shares_str = ""
                        if shares is not None:
                            s = float(shares)
                            if abs(s) >= 1e9:
                                shares_str = f" ({s/1e9:.2f}B 股)"
                            elif abs(s) >= 1e6:
                                shares_str = f" ({s/1e6:.2f}M 股)"
                            else:
                                shares_str = f" ({int(s):,} 股)"
                        change_str = ""
                        if pct_change is not None:
                            chg = float(pct_change) * 100
                            arrow = "▲" if chg > 0 else ("▼" if chg < 0 else "—")
                            change_str = f" {arrow}{abs(chg):.1f}%"
                        lines.append(f"  {holder}: {pct_str}{shares_str}{change_str}")
                else:
                    lines.append("  資料不足")
            except Exception as e:
                lines.append(f"  資料不足: {str(e)}")

        return "\n".join(lines)
    except Exception as e:
        return f"無法取得 {ticker} 的機構法人資料: {str(e)}"


@mcp.tool()
def get_volume_analysis(ticker: str) -> str:
    """
    交易量與散戶/法人參與率分析。
    包含：成交量概況、換手率、持股結構（機構/散戶估算）、台股三大法人日參與率、空頭比率、散戶集中度評估。
    例如: 'AAPL', '2330.TW', '6667.TWO'
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        name = info.get('longName', ticker)
        is_tw = ticker.upper().endswith('.TW')
        is_two = ticker.upper().endswith('.TWO')
        is_taiwan = is_tw or is_two
        ticker_base = ticker.split('.')[0]

        lines = [f"=== {ticker} ({name}) 交易量與散戶/法人分析 ===", ""]

        # 【交易量概況】
        lines.append("【交易量概況】")
        hist_60 = None
        ma10_vol = None
        try:
            hist_60 = stock.history(period="60d")
            if hist_60 is not None and not hist_60.empty and 'Volume' in hist_60.columns:
                vol = hist_60['Volume']
                latest_vol = float(vol.iloc[-1])
                ma10_vol = float(vol.tail(10).mean())
                ma60_vol = float(vol.mean())
                vol_ratio = latest_vol / ma10_vol if ma10_vol > 0 else None

                def fmt_vol(v):
                    if v >= 1e8:
                        return f"{v / 1e8:.2f}億"
                    elif v >= 1e4:
                        return f"{v / 1e4:.0f}萬"
                    return f"{v:,.0f}"

                lines.append(f"  最近一日成交量: {fmt_vol(latest_vol)}")
                lines.append(f"  10 日均量: {fmt_vol(ma10_vol)}")
                lines.append(f"  60 日均量: {fmt_vol(ma60_vol)}")

                if vol_ratio is not None:
                    if vol_ratio > 1.5:
                        vol_state = "爆量 ⚡"
                    elif vol_ratio < 0.5:
                        vol_state = "縮量 ↓"
                    else:
                        vol_state = "正常"
                    lines.append(f"  量比 (近日/10日均): {vol_ratio:.2f}x → {vol_state}")

                float_shares = info.get('floatShares')
                if float_shares and float_shares > 0 and ma10_vol > 0:
                    turnover_daily = ma10_vol / float_shares * 100
                    turnover_monthly = turnover_daily * 21
                    lines.append(f"  換手率估算（10日均量/流通股）: {turnover_daily:.2f}%/日")
                    lines.append(f"  月化換手率估算: {turnover_monthly:.1f}%")
                    if turnover_monthly > 30:
                        lines.append("  ⚠️  換手率偏高，散戶頻繁進出")
                    elif turnover_monthly > 10:
                        lines.append("  → 換手率中等")
                    else:
                        lines.append("  ✓ 換手率偏低，持股穩定")
                else:
                    lines.append("  換手率: 流通股資料不足，無法計算")
            else:
                lines.append("  成交量資料不足")
        except Exception as e:
            lines.append(f"  成交量資料取得失敗: {str(e)}")

        # 【持股結構】
        lines.append("")
        lines.append("【持股結構】")
        inst_pct_val = None
        insider_pct_val = None
        retail_pct_val = None
        try:
            inst_pct_raw = info.get('heldPercentInstitutions')
            insider_pct_raw = info.get('heldPercentInsiders')
            inst_count = info.get('institutionsCount')

            if inst_pct_raw is None:
                try:
                    mh = stock.major_holders
                    if mh is not None and not mh.empty:
                        def get_mh_val(key):
                            if key in mh.index:
                                return mh.loc[key].iloc[0]
                            return None
                        inst_pct_raw = get_mh_val('institutionsPercentHeld')
                        if insider_pct_raw is None:
                            insider_pct_raw = get_mh_val('insidersPercentHeld')
                        if inst_count is None:
                            inst_count = get_mh_val('institutionsCount')
                except Exception:
                    pass

            if inst_pct_raw is not None:
                inst_pct_val = float(inst_pct_raw) * 100
                lines.append(f"  機構持股: {inst_pct_val:.2f}%")
            else:
                lines.append("  機構持股: 資料不足")

            if insider_pct_raw is not None:
                insider_pct_val = float(insider_pct_raw) * 100
                lines.append(f"  內部人持股: {insider_pct_val:.2f}%")
            else:
                lines.append("  內部人持股: 資料不足")

            if inst_count is not None:
                lines.append(f"  機構家數: {int(float(inst_count))}")

            if inst_pct_val is not None and insider_pct_val is not None:
                retail_pct_val = max(0.0, 100.0 - inst_pct_val - insider_pct_val)
                lines.append(f"  估算散戶持股: {retail_pct_val:.2f}% （= 100% − 機構 − 內部人）")
            elif inst_pct_val is not None:
                retail_pct_val = max(0.0, 100.0 - inst_pct_val)
                lines.append(f"  估算散戶持股: {retail_pct_val:.2f}% （僅扣除機構）")
            else:
                lines.append("  估算散戶持股: 持股資料不足，無法計算")
        except Exception as e:
            lines.append(f"  持股結構資料取得失敗: {str(e)}")

        # 【法人日交易參與率】（台股專用）
        if is_taiwan:
            lines.append("")
            lines.append("【法人日交易參與率（台股）】")
            try:
                def get_recent_weekdays_va(n=10):
                    days = []
                    d = datetime.date.today()
                    while len(days) < n:
                        if d.weekday() < 5:
                            days.append(d)
                        d -= datetime.timedelta(days=1)
                    return days

                def parse_tw_amount(v):
                    v = str(v).strip()
                    if not v or v == '-':
                        return None
                    return int(v.replace(',', ''))

                recent_dates_va = get_recent_weekdays_va(10)
                participation_found = False

                for d in recent_dates_va:
                    date_str = d.strftime('%Y%m%d')
                    try:
                        url_inst = f"https://www.twse.com.tw/rwd/zh/fund/TWT44U?response=json&date={date_str}&stockNo={ticker_base}"
                        resp_inst = httpx.get(url_inst, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
                        data_inst = resp_inst.json()

                        if data_inst.get('stat') != 'OK':
                            continue

                        fields_inst = data_inst.get('fields', [])
                        rows_inst = data_inst.get('data', [])
                        if not rows_inst:
                            continue

                        buy_idx = None
                        sell_idx = None
                        for i, f in enumerate(fields_inst):
                            if '買進' in f and '金額' in f:
                                buy_idx = i
                            if '賣出' in f and '金額' in f:
                                sell_idx = i
                        if buy_idx is None:
                            buy_idx = 1
                        if sell_idx is None:
                            sell_idx = 2

                        total_inst_buy = 0
                        total_inst_sell = 0
                        for row in rows_inst:
                            b = parse_tw_amount(row[buy_idx]) if buy_idx < len(row) else None
                            s = parse_tw_amount(row[sell_idx]) if sell_idx < len(row) else None
                            if b is not None:
                                total_inst_buy += b
                            if s is not None:
                                total_inst_sell += s

                        total_inst_amount = total_inst_buy + total_inst_sell
                        if total_inst_amount == 0:
                            continue

                        url_day = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={date_str}&stockNo={ticker_base}"
                        resp_day = httpx.get(url_day, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
                        data_day = resp_day.json()

                        if data_day.get('stat') != 'OK':
                            continue

                        fields_day = data_day.get('fields', [])
                        rows_day = data_day.get('data', [])
                        if not rows_day:
                            continue

                        amount_idx = None
                        for i, f in enumerate(fields_day):
                            if '成交金額' in f:
                                amount_idx = i
                                break
                        if amount_idx is None:
                            amount_idx = 2

                        tw_year = d.year - 1911
                        tw_date_str = f"{tw_year}/{d.month:02d}/{d.day:02d}"
                        target_row = None
                        for row in rows_day:
                            if row and row[0] == tw_date_str:
                                target_row = row
                                break
                        if target_row is None:
                            target_row = rows_day[-1]

                        total_amount_raw = parse_tw_amount(target_row[amount_idx]) if amount_idx < len(target_row) else None
                        if total_amount_raw is None or total_amount_raw == 0:
                            continue

                        inst_pct_trade = total_inst_amount / total_amount_raw * 100
                        retail_pct_trade = 100.0 - inst_pct_trade

                        def fmt_tw_amt(v):
                            if v >= 1e8:
                                return f"{v / 1e8:.2f}億"
                            elif v >= 1e4:
                                return f"{v / 1e4:.0f}萬"
                            return f"{v:,.0f}"

                        lines.append(f"  資料日期: {d.strftime('%Y-%m-%d')}")
                        lines.append(f"  法人買進金額: {fmt_tw_amt(total_inst_buy)}")
                        lines.append(f"  法人賣出金額: {fmt_tw_amt(total_inst_sell)}")
                        lines.append(f"  法人交易總額: {fmt_tw_amt(total_inst_amount)}")
                        lines.append(f"  當日總成交金額: {fmt_tw_amt(total_amount_raw)}")
                        lines.append(f"  法人參與率: {inst_pct_trade:.1f}%")
                        lines.append(f"  估算散戶參與率: {retail_pct_trade:.1f}%")
                        if inst_pct_trade < 20:
                            lines.append("  ⚠️  法人參與率偏低（< 20%），散戶主導")
                        elif inst_pct_trade > 50:
                            lines.append("  ✓ 法人參與率高（> 50%），法人主導")
                        participation_found = True
                        break

                    except Exception:
                        continue

                if not participation_found:
                    lines.append("  無法取得 TWT44U 法人參與率資料，顯示 T86 淨買賣超：")
                    try:
                        for d in recent_dates_va[:5]:
                            date_str = d.strftime('%Y%m%d')
                            url_t86 = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}&selectType=ALL"
                            resp = httpx.get(url_t86, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
                            data = resp.json()
                            if data.get('stat') != 'OK':
                                continue
                            fields = data.get('fields', [])
                            rows = data.get('data', [])
                            for row in rows:
                                if row and row[0] == ticker_base:
                                    total_idx = None
                                    for i, f in enumerate(fields):
                                        if '三大法人' in f and '買賣超' in f:
                                            total_idx = i
                                            break
                                    if total_idx is not None and total_idx < len(row):
                                        lines.append(f"  {d.strftime('%Y-%m-%d')} 三大法人淨買超: {row[total_idx]} 股（無法精確計算參與率）")
                                    break
                            break
                    except Exception:
                        lines.append("  法人備援資料取得失敗")

            except Exception as e:
                lines.append(f"  台股法人參與率計算失敗: {str(e)}")

        # 【散戶投機指標】（非台股）
        else:
            lines.append("")
            lines.append("【散戶投機指標（美股）】")
            try:
                short_ratio = info.get('shortRatio')
                short_pct_float = info.get('shortPercentOfFloat')
                shares_short = info.get('sharesShort')

                if short_ratio is not None:
                    if short_ratio > 7:
                        short_state = "⚠️  高度投機（> 7 天）"
                    elif short_ratio > 3:
                        short_state = "→ 偏高（> 3 天）"
                    else:
                        short_state = "✓ 正常"
                    lines.append(f"  空頭比率 (Days to Cover): {short_ratio:.1f} 天 → {short_state}")
                else:
                    lines.append("  空頭比率: 資料不足")

                if short_pct_float is not None:
                    lines.append(f"  空頭佔流通股: {short_pct_float * 100:.2f}%")

                if shares_short is not None:
                    s = float(shares_short)
                    if s >= 1e9:
                        s_str = f"{s / 1e9:.2f}B 股"
                    elif s >= 1e6:
                        s_str = f"{s / 1e6:.2f}M 股"
                    else:
                        s_str = f"{int(s):,} 股"
                    lines.append(f"  空頭持倉: {s_str}")

                if short_ratio is None and short_pct_float is None:
                    lines.append("  無空頭資料（可能為 ETF 或非美股）")
            except Exception as e:
                lines.append(f"  投機指標資料取得失敗: {str(e)}")

        # 【散戶集中度評估】
        lines.append("")
        lines.append("【散戶集中度評估】")
        try:
            score_retail = 0
            score_total = 0
            eval_signals = []

            if retail_pct_val is not None:
                score_total += 1
                if retail_pct_val > 60:
                    score_retail += 1
                    eval_signals.append(f"  ⚠️  散戶估算持股 {retail_pct_val:.1f}% > 60%（偏高）")
                else:
                    eval_signals.append(f"  ✓ 散戶估算持股 {retail_pct_val:.1f}%（正常）")

            float_shares = info.get('floatShares')
            if float_shares and float_shares > 0 and ma10_vol is not None and ma10_vol > 0:
                turnover_monthly = ma10_vol / float_shares * 100 * 21
                score_total += 1
                if turnover_monthly > 30:
                    score_retail += 1
                    eval_signals.append(f"  ⚠️  月化換手率 {turnover_monthly:.1f}% > 30%（散戶頻繁進出）")
                else:
                    eval_signals.append(f"  ✓ 月化換手率 {turnover_monthly:.1f}%（正常）")

            if not is_taiwan:
                short_ratio = info.get('shortRatio')
                if short_ratio is not None:
                    score_total += 1
                    if short_ratio > 5:
                        score_retail += 1
                        eval_signals.append(f"  ⚠️  空頭比率 {short_ratio:.1f} 天 > 5（投機偏高）")
                    else:
                        eval_signals.append(f"  ✓ 空頭比率 {short_ratio:.1f} 天（正常）")

            for s in eval_signals:
                lines.append(s)

            if score_total > 0:
                lines.append("")
                retail_ratio = score_retail / score_total
                if retail_ratio >= 0.5:
                    lines.append("  → 綜合結論：散戶比例偏高 ⚠️  — 建議謹慎，法人參與度較低")
                elif retail_ratio > 0:
                    lines.append("  → 綜合結論：法人/散戶混合 → — 中性，建議搭配其他指標判斷")
                else:
                    lines.append("  → 綜合結論：法人主導 ✓ — 符合法人偏好標的特徵")
            else:
                lines.append("  資料不足，無法評估散戶集中度")

        except Exception as e:
            lines.append(f"  散戶集中度評估失敗: {str(e)}")

        return "\n".join(lines)
    except Exception as e:
        return f"無法取得 {ticker} 的交易量分析: {str(e)}"


@mcp.tool()
def get_stock_report(ticker: str) -> str:
    """
    綜合投資報告：整合估值、技術面、基本面、股息分析，輸出完整參考報告。
    例如: 'AAPL', '2330.TW'
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        name = info.get('longName', ticker)
        sector = info.get('sector', 'N/A')
        industry = info.get('industry', 'N/A')
        currency = info.get('currency', 'N/A')
        market_cap = info.get('marketCap')
        current_price = info.get('currentPrice') or info.get('regularMarketPrice')

        def fmt_market_cap(mc):
            if not mc:
                return 'N/A'
            if mc >= 1e12:
                return f"{mc / 1e12:.2f}T {currency}"
            elif mc >= 1e9:
                return f"{mc / 1e9:.2f}B {currency}"
            elif mc >= 1e6:
                return f"{mc / 1e6:.2f}M {currency}"
            return f"{mc:.0f} {currency}"

        price_str = f"{current_price:.2f} {currency}" if current_price else "N/A"

        lines = [
            "=" * 50,
            f"  {ticker} ({name}) 投資參考報告",
            "=" * 50,
            f"產業: {sector} / {industry}",
            f"市值: {fmt_market_cap(market_cap)}",
            f"目前價格: {price_str}",
            "",
        ]

        # 估值摘要
        lines.append("【估值摘要】")
        trailing_pe = info.get('trailingPE')
        forward_pe = info.get('forwardPE')
        peg = info.get('pegRatio')
        pb = info.get('priceToBook')

        if trailing_pe:
            lines.append(f"  Trailing P/E: {trailing_pe:.2f}")
        if forward_pe:
            lines.append(f"  Forward P/E:  {forward_pe:.2f}")
        if pb:
            lines.append(f"  P/B Ratio:    {pb:.2f}")
        if peg is not None:
            lines.append(f"  PEG Ratio:    {peg:.2f}")

        try:
            eps = info.get('trailingEps')
            bvps = info.get('bookValue')
            if eps and bvps and eps > 0 and bvps > 0 and current_price:
                graham = math.sqrt(22.5 * eps * bvps)
                ratio = current_price / graham
                lines.append(f"  Graham Number: {graham:.2f} {currency} (現價是 Graham 的 {ratio:.2f}x)")
        except Exception:
            pass

        # 技術面摘要
        lines.append("")
        lines.append("【技術面摘要】")
        try:
            hist = stock.history(period="1y")
            if not hist.empty:
                close = hist['Close']
                curr = close.iloc[-1]

                if len(close) >= 50:
                    ma50 = close.rolling(50).mean().iloc[-1]
                    lines.append(f"  MA50:  {ma50:.2f} ({(curr - ma50) / ma50 * 100:+.1f}%)")

                if len(close) >= 200:
                    ma200 = close.rolling(200).mean().iloc[-1]
                    lines.append(f"  MA200: {ma200:.2f} ({(curr - ma200) / ma200 * 100:+.1f}%)")
                    ma50_val = close.rolling(50).mean().iloc[-1]
                    state = "多頭排列（MA50 > MA200）" if ma50_val > ma200 else "空頭排列（MA50 < MA200）"
                    lines.append(f"  → {state}")

                if len(close) >= 15:
                    delta = close.diff()
                    avg_gain = delta.clip(lower=0).rolling(14).mean().iloc[-1]
                    avg_loss = (-delta.clip(upper=0)).rolling(14).mean().iloc[-1]
                    rsi = 100 - (100 / (1 + avg_gain / avg_loss)) if avg_loss != 0 else 100.0
                    rsi_state = "超買" if rsi > 70 else ("超賣" if rsi < 30 else "中性")
                    lines.append(f"  RSI(14): {rsi:.1f} ({rsi_state})")
        except Exception as e:
            lines.append(f"  技術指標取得失敗: {str(e)}")

        week52_high = info.get('fiftyTwoWeekHigh')
        week52_low = info.get('fiftyTwoWeekLow')
        if week52_high and week52_low and current_price:
            from_high = (current_price - week52_high) / week52_high * 100
            lines.append(f"  52週高點: {week52_high:.2f}，距高點 {from_high:.1f}%")

        # 基本面摘要
        lines.append("")
        lines.append("【基本面摘要】")
        gross_margin = info.get('grossMargins')
        operating_margin = info.get('operatingMargins')
        revenue_growth = info.get('revenueGrowth')
        earnings_growth = info.get('earningsGrowth')

        if gross_margin is not None:
            lines.append(f"  毛利率: {gross_margin * 100:.1f}%")
        if operating_margin is not None:
            lines.append(f"  營業利益率: {operating_margin * 100:.1f}%")
        if revenue_growth is not None:
            lines.append(f"  營收成長率: {revenue_growth * 100:+.1f}%")
        if earnings_growth is not None:
            lines.append(f"  獲利成長率: {earnings_growth * 100:+.1f}%")

        debt_to_equity = info.get('debtToEquity')
        if debt_to_equity is not None:
            lines.append(f"  D/E 比率: {debt_to_equity:.1f}%")

        try:
            cashflow = stock.cashflow
            if cashflow is not None and not cashflow.empty:
                ocf = None
                for rn in ['Operating Cash Flow', 'Total Cash From Operating Activities']:
                    if rn in cashflow.index:
                        ocf = cashflow.loc[rn].iloc[0]
                        break
                capex = None
                for rn in ['Capital Expenditure', 'Capital Expenditures']:
                    if rn in cashflow.index:
                        capex = cashflow.loc[rn].iloc[0]
                        break
                if ocf is not None:
                    fcf = ocf + capex if capex is not None else ocf
                    fcf_sign = "正值 ✓" if fcf > 0 else "負值 ✗"

                    def fmt(v):
                        return f"{v / 1e9:.2f}B" if abs(v) >= 1e9 else f"{v / 1e6:.2f}M"

                    lines.append(f"  自由現金流: {fmt(fcf)} {currency} ({fcf_sign})")
        except Exception:
            pass

        # 股息摘要
        lines.append("")
        lines.append("【股息摘要】")
        div_yield = info.get('dividendYield')
        payout = info.get('payoutRatio')

        if div_yield:
            lines.append(f"  殖利率: {div_yield * 100:.2f}%")
        else:
            lines.append("  殖利率: 目前未配息")
        if payout:
            lines.append(f"  配息率: {payout * 100:.1f}%")

        # 整體評估
        lines.append("")
        lines.append("【整體評估（僅供參考，非投資建議）】")

        signals = []
        if trailing_pe:
            if trailing_pe < 15:
                signals.append(("估值(P/E)", "偏低", "+"))
            elif trailing_pe > 30:
                signals.append(("估值(P/E)", "偏高", "-"))
            else:
                signals.append(("估值(P/E)", "合理", "~"))

        if peg is not None:
            if 0 < peg < 1:
                signals.append(("PEG", "成長股折價", "+"))
            elif peg > 2:
                signals.append(("PEG", "偏高", "-"))

        if gross_margin is not None:
            if gross_margin >= 0.4:
                signals.append(("毛利率", "優秀", "+"))
            elif gross_margin < 0.15:
                signals.append(("毛利率", "偏低", "-"))

        if div_yield and div_yield >= 0.04:
            signals.append(("殖利率", "高殖利率", "+"))

        try:
            inst_pct_report = info.get('heldPercentInstitutions')
            insider_pct_report = info.get('heldPercentInsiders')
            if inst_pct_report is not None and insider_pct_report is not None:
                inst_pct_f = float(inst_pct_report) * 100
                insider_pct_f = float(insider_pct_report) * 100
                retail_pct_f = max(0.0, 100.0 - inst_pct_f - insider_pct_f)
                if retail_pct_f > 60:
                    signals.append(("持股結構", "散戶比例偏高", "-"))
                elif inst_pct_f > 60:
                    signals.append(("持股結構", "法人主導", "+"))
        except Exception:
            pass

        if signals:
            for category, desc, sign in signals:
                icon = "✓" if sign == "+" else ("✗" if sign == "-" else "→")
                lines.append(f"  {icon} {category}: {desc}")

        positive = sum(1 for _, _, s in signals if s == "+")
        negative = sum(1 for _, _, s in signals if s == "-")

        lines.append("")
        if positive > negative + 1:
            lines.append("  綜合評估: 多項指標偏正面，可進一步研究")
        elif negative > positive + 1:
            lines.append("  綜合評估: 多項指標偏負面，建議謹慎評估")
        else:
            lines.append("  綜合評估: 指標混合，建議深入研究後再決策")

        lines.append("")
        lines.append("⚠️  以上分析僅供參考，不構成任何投資建議。投資有風險，請自行評估。")
        lines.append("=" * 50)

        return "\n".join(lines)
    except Exception as e:
        return f"無法生成 {ticker} 的綜合報告: {str(e)}"


if __name__ == "__main__":
    mcp.run()
