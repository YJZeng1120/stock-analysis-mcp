from mcp.server.fastmcp import FastMCP
import yfinance as yf
import math

# 建立 MCP Server 實例
mcp = FastMCP("stock-analysis-mcp")


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
