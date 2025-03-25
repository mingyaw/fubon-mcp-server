# Fubon MCP Server

富邦證券市場資料 MCP (Model Communication Protocol) 伺服器，用於獲取台股歷史數據。

## 功能特點

- 支援台股及 ETF 歷史 K 線數據查詢
- 本地數據快取，減少 API 呼叫次數
- 自動分段處理長時間區間的數據請求
- 支援數據去重和排序
- 提供額外計算欄位（成交值、漲跌、漲跌幅）

## 系統需求

- Python 3.8 或以上版本
- 富邦證券電子憑證
- macOS / Linux / Windows

## 安裝說明

1. 克隆專案：

```bash
git clone https://github.com/yourusername/fubon-mcp-server.git
cd fubon-mcp-server
```

2. 建立虛擬環境：

```bash
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# 或
.venv\Scripts\activate  # Windows
```

3. 安裝相依套件：

```bash
pip install -r requirements.txt
```

4. 設定環境變數：

將以下環境變數加入到 `.env` 檔案：

```bash
FUBON_USERNAME=您的富邦證券帳號
FUBON_PASSWORD=您的富邦證券密碼
FUBON_PFX_PATH=/path/to/your/certificate.pfx
FUBON_DATA_DIR=/path/to/your/data/directory
```

## 使用方法

1. 啟動伺服器：

```bash
python server.py
```

2. 在 VS Code 中設定 MCP：

在 VS Code 的設定檔中加入：

```json
{
  "mcpServers": {
    "fubon-mcp-server": {
      "command": "/path/to/your/.venv/bin/python3",
      "args": ["/path/to/your/server.py"],
      "env": {
        "FUBON_USERNAME": "您的富邦證券帳號",
        "FUBON_PASSWORD": "您的富邦證券密碼",
        "FUBON_PFX_PATH": "/path/to/your/certificate.pfx",
        "FUBON_DATA_DIR": "/path/to/your/data/directory"
      }
    }
  }
}
```

## API 說明

### 取得歷史 K 線數據

```python
historical_candles({
    "symbol": "2330",      # 股票代碼
    "from_date": "2024-03-01",  # 起始日期
    "to_date": "2024-03-24"     # 結束日期
})
```

### 查詢本地歷史數據

```
GET twstock://{symbol}/historical
```

## 注意事項

- 請妥善保管您的富邦證券帳號密碼和電子憑證
- 建議設定適當的數據快取目錄
- API 呼叫可能有每日次數限制
- 長時間區間的數據會自動分段請求

## 授權條款

MIT License

## 貢獻指南

歡迎提交 Issue 和 Pull Request

## 作者

Hans Li

## 更新日誌

### v0.1.0

- 初始版本發布
- 支援基本的歷史數據查詢
- 實作本地數據快取
