#!/usr/bin/env python3
import sys
import os
import json
import pandas as pd
from datetime import datetime
from pathlib import Path
import tempfile
import shutil
from mcp.server.fastmcp import FastMCP
from fubon_neo.sdk import FubonSDK
from typing import Dict
from pydantic import BaseModel, field_validator

# 設置數據目錄
default_data_dir = Path.home() / "Library" / "Application Support" / "fubon-mcp" / "data"
BASE_DATA_DIR = Path(os.getenv('FUBON_DATA_DIR', default_data_dir))

# 確保數據目錄存在
BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)
print(f"使用數據目錄: {BASE_DATA_DIR}", file=sys.stderr)

# 從環境變量獲取認證信息
username = os.getenv('FUBON_USERNAME')
password = os.getenv('FUBON_PASSWORD')
pfx_path = os.getenv('FUBON_PFX_PATH')

if not all([username, password, pfx_path]):
    raise ValueError('FUBON_USERNAME, FUBON_PASSWORD, and FUBON_PFX_PATH environment variables are required')

# 創建 MCP 服務器
mcp = FastMCP("fubon-market-data")

# 初始化富邦API客戶端
sdk = FubonSDK()
accounts = sdk.login(username, password, pfx_path)
sdk.init_realtime()
reststock = sdk.marketdata.rest_client.stock


def read_local_stock_data(stock_code):
    """讀取本地股票CSV數據"""
    try:
        file_path = BASE_DATA_DIR / f"{stock_code}.csv"
        if not file_path.exists():
            return None
        
        df = pd.read_csv(file_path)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values(by='date', ascending=False)
        return df
    except Exception as e:
        print(f"讀取CSV檔案時發生錯誤: {str(e)}", file=sys.stderr)
        return None

def save_to_local_csv(symbol: str, new_data: list):
    """將新數據保存到本地CSV，避免重複數據"""
    try:
        file_path = BASE_DATA_DIR / f"{symbol}.csv"
        new_df = pd.DataFrame(new_data)
        new_df['date'] = pd.to_datetime(new_df['date'])
        
        # 創建臨時檔案
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as temp_file:
            temp_path = Path(temp_file.name)
            
            try:
                if file_path.exists():
                    # 讀取現有數據
                    existing_df = pd.read_csv(file_path)
                    existing_df['date'] = pd.to_datetime(existing_df['date'])
                    
                    # 合併數據並刪除重複項
                    combined_df = pd.concat([existing_df, new_df])
                    combined_df = combined_df.drop_duplicates(subset=['date'], keep='last')
                    combined_df = combined_df.sort_values(by='date', ascending=False)
                else:
                    combined_df = new_df.sort_values(by='date', ascending=False)
                
                # 將合併後的數據寫入臨時檔案
                combined_df.to_csv(temp_path, index=False)
                
                # 原子性地替換原檔案
                shutil.move(str(temp_path), str(file_path))
                print(f"成功保存數據到 {file_path}", file=sys.stderr)
                
            except Exception as e:
                # 確保清理臨時檔案
                if temp_path.exists():
                    temp_path.unlink()
                raise e
                
    except Exception as e:
        print(f"保存CSV檔案時發生錯誤: {str(e)}", file=sys.stderr)

@mcp.resource("twstock://{symbol}/historical")
def get_historical_data(symbol):
    """提供本地歷史股價數據"""
    try:
        data = read_local_stock_data(symbol)
        if data is None:
            return {
                'status': 'error',
                'data': [],
                'message': f'找不到股票代碼 {symbol} 的數據'
            }
        
        return {
            'status': 'success',
            'data': data,
            'message': f'成功獲取 {symbol} 的歷史數據'
        }
    except Exception as e:
        return {
            'status': 'error',
            'data': [],
            'message': f'獲取數據時發生錯誤: {str(e)}'
        }

class HistoricalCandlesArgs(BaseModel):
    symbol: str
    from_date: str
    to_date: str
    
@mcp.tool()
def historical_candles(args: Dict) -> dict:
    """
    獲取歷史數據，優先使用本地數據，如果本地沒有再使用 API
    
    Args:
        symbol (str): 股票代碼，必須為文字格式，例如: '2330'、'00878'
        from_date (str): 開始日期，格式: YYYY-MM-DD
        to_date (str): 結束日期，格式: YYYY-MM-DD
    """
    try:
        # 使用 HistoricalCandlesArgs 進行驗證
        validated_args = HistoricalCandlesArgs(**args) 
        # 從驗證後的物件取得參數
        symbol = validated_args.symbol
        from_date = validated_args.from_date
        to_date = validated_args.to_date

        # 先檢查本地數據
        local_data = read_local_stock_data(symbol)
        
        if local_data is not None:
            df = local_data
            # 過濾指定日期範圍的數據
            mask = (df['date'] >= from_date) & (df['date'] <= to_date)
            df = df[mask]
            
            if not df.empty:
                df = df.sort_values(by='date', ascending=False)
                # 確保所需的計算欄位存在
                if 'vol_value' not in df.columns:
                    df['vol_value'] = df['close'] * df['volume']  # 成交值
                if 'price_change' not in df.columns:
                    df['price_change'] = df['close'] - df['open']  # 漲跌
                if 'change_ratio' not in df.columns:
                    df['change_ratio'] = (df['close'] - df['open']) / df['open'] * 100  # 漲跌幅
                result_data = df.to_dict('records')
                return {
                    'status': 'success',
                    'data': result_data,
                    'message': f'成功從本地數據獲取 {symbol} 從 {from_date} 到 {to_date} 的數據'
                }

        # 如果本地沒有數據或日期範圍內沒有數據，使用 API
        # 轉換日期字串為 datetime 物件
        from_datetime = pd.to_datetime(from_date)
        to_datetime = pd.to_datetime(to_date)
        
        # 計算日期差異
        date_diff = (to_datetime - from_datetime).days
        
        # 存儲所有分段資料
        all_data = []
        
        # 如果日期間隔超過一年，進行分段
        if date_diff > 365:
            current_from = from_datetime
            while current_from < to_datetime:
                # 計算當前段的結束日期
                current_to = min(current_from + pd.Timedelta(days=365), to_datetime)
                
                # 準備 API 參數
                params = {
                    "symbol": symbol,
                    "from": current_from.strftime('%Y-%m-%d'),
                    "to": current_to.strftime('%Y-%m-%d')
                }
                
                try:
                    print(f"正在獲取 {symbol} 從 {params['from']} 到 {params['to']} 的數據...", file=sys.stderr)
                    response = reststock.historical.candles(**params)
                    print(f"API 回應內容: {response}", file=sys.stderr)
                    
                    if isinstance(response, dict):
                        if 'data' in response and response['data']:
                            segment_data = response['data']
                            all_data.extend(segment_data)
                            print(f"成功獲取 {len(segment_data)} 筆資料", file=sys.stderr)
                        else:
                            print(f"API 回應無資料: {response}", file=sys.stderr)
                    else:
                        print(f"API 回應格式錯誤: {response}", file=sys.stderr)
                except Exception as segment_error:
                    print(f"獲取分段資料時發生錯誤: {str(segment_error)}", file=sys.stderr)
                
                # 更新下一段的開始日期
                current_from = current_to + pd.Timedelta(days=1)
        else:
            # 如果間隔小於一年，直接取得資料
            params = {
                "symbol": symbol,
                "from": from_date,
                "to": to_date
            }
            
            try:
                print(f"正在獲取 {symbol} 從 {params['from']} 到 {params['to']} 的數據...", file=sys.stderr)
                response = reststock.historical.candles(**params)
                print(f"API 回應內容: {response}", file=sys.stderr)
                
                if isinstance(response, dict):
                    if 'data' in response and response['data']:
                        all_data = response['data']
                        print(f"成功獲取 {len(all_data)} 筆資料", file=sys.stderr)
                    else:
                        print(f"API 回應無資料: {response}", file=sys.stderr)
                else:
                    print(f"API 回應格式錯誤: {response}", file=sys.stderr)
            except Exception as api_error:
                print(f"API 呼叫發生錯誤: {str(api_error)}", file=sys.stderr)
        
        # 處理合併後的資料
        if all_data:
            df = pd.DataFrame(all_data)
            df = df.sort_values(by='date', ascending=False)
            # 添加更多資訊欄位
            df['vol_value'] = df['close'] * df['volume']  # 成交值
            df['price_change'] = df['close'] - df['open']  # 漲跌
            df['change_ratio'] = (df['close'] - df['open']) / df['open'] * 100  # 漲跌幅
            # 保存 API 數據到本地
            save_to_local_csv(symbol, all_data)
            
            data = df.to_dict('records')
        else:
            data = []
            
        return {
            'status': 'success',
            'data': data,
            'message': f'成功獲取 {symbol} 從 {from_date} 到 {to_date} 的數據'
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'data': [],
            'message': f'獲取數據時發生錯誤: {str(e)}'
        }

if __name__ == "__main__":
    try:
        print('富邦證券MCP server運行中...', file=sys.stderr)
        mcp.run()
    except Exception as e:
        print(f"啟動伺服器時發生錯誤: {str(e)}", file=sys.stderr)
        sys.exit(1)
