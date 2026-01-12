"""
결과 추적 모듈
전날 선정 종목의 다음날 실적을 기록
"""

import os
import glob
from datetime import datetime, timedelta
import pandas as pd
import FinanceDataReader as fdr

from config import OUTPUT_DIR


def get_previous_excel_file():
    """가장 최근 Excel 파일 찾기"""
    pattern = os.path.join(OUTPUT_DIR, "top100_*.xlsx")
    files = glob.glob(pattern)

    if not files:
        return None

    # 수정 시간 기준 정렬 (최신순)
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]


def get_today_prices(codes):
    """오늘 날짜 종가 일괄 조회"""
    today = datetime.now()
    start_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    prices = {}
    changes = {}
    trade_date = None

    for code in codes:
        try:
            df = fdr.DataReader(code, start_date, end_date)
            if not df.empty:
                # 가장 최근 거래일 데이터
                latest = df.iloc[-1]
                prices[code] = int(latest['Close'])

                # 등락률 계산 (전일 대비)
                if len(df) >= 2:
                    prev_close = df.iloc[-2]['Close']
                    changes[code] = round((latest['Close'] - prev_close) / prev_close * 100, 2)
                else:
                    changes[code] = 0

                if trade_date is None:
                    trade_date = df.index[-1].strftime("%Y%m%d")
        except Exception as e:
            prices[code] = None
            changes[code] = None

    return prices, changes, trade_date or today.strftime("%Y%m%d")


def update_with_next_day_results(excel_path=None):
    """
    Excel 파일에 다음날 결과 추가

    Args:
        excel_path: 업데이트할 Excel 파일 경로 (없으면 가장 최근 파일)

    Returns:
        업데이트된 파일 경로
    """
    if excel_path is None:
        excel_path = get_previous_excel_file()

    if excel_path is None or not os.path.exists(excel_path):
        print("[추적] Excel 파일을 찾을 수 없습니다.")
        return None

    print(f"[추적] 파일 로드: {excel_path}")

    # Excel 읽기
    df = pd.read_excel(excel_path)

    # 이미 다음날 결과가 있는지 확인
    if '다음날종가' in df.columns:
        print("[추적] 이미 다음날 결과가 기록되어 있습니다.")
        return excel_path

    # 종목코드 리스트
    codes = df['종목코드'].astype(str).str.zfill(6).tolist()

    print(f"[추적] {len(codes)}개 종목 가격 조회 중...")

    # 오늘 가격 조회
    prices, changes, trade_date = get_today_prices(codes)

    print(f"[추적] 거래일: {trade_date}")

    # 새 컬럼 추가
    df['다음날종가'] = df['종목코드'].astype(str).str.zfill(6).map(prices)
    df['다음날등락률(%)'] = df['종목코드'].astype(str).str.zfill(6).map(changes)

    # 수익률 계산 (선정일 종가 대비)
    df['수익률(%)'] = ((df['다음날종가'] - df['현재가']) / df['현재가'] * 100).round(2)

    # 거래일 기록
    df['결과기록일'] = trade_date

    # 저장
    df.to_excel(excel_path, index=False, engine='openpyxl')

    # 통계 출력
    valid_returns = df['수익률(%)'].dropna()
    if len(valid_returns) > 0:
        print(f"\n[추적] 결과 요약:")
        print(f"    - 평균 수익률: {valid_returns.mean():.2f}%")
        print(f"    - 최대 수익률: {valid_returns.max():.2f}%")
        print(f"    - 최소 수익률: {valid_returns.min():.2f}%")
        print(f"    - 상승 종목: {(valid_returns > 0).sum()}개")
        print(f"    - 하락 종목: {(valid_returns < 0).sum()}개")

    print(f"\n[추적] 파일 업데이트 완료: {excel_path}")

    return excel_path


def track_all_previous_files():
    """모든 이전 파일의 결과 추적"""
    pattern = os.path.join(OUTPUT_DIR, "top100_*.xlsx")
    files = glob.glob(pattern)

    for f in sorted(files):
        df = pd.read_excel(f)
        if '다음날종가' not in df.columns:
            print(f"\n{'='*50}")
            update_with_next_day_results(f)


if __name__ == "__main__":
    # 가장 최근 파일 업데이트
    update_with_next_day_results()
