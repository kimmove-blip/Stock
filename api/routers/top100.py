"""
AI 추천 TOP 100 API 라우터
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime, timedelta
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.schemas.stock import Top100Item, Top100Response


router = APIRouter()

# TOP 100 결과 저장 경로
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'output')


def get_latest_top100_file() -> Optional[str]:
    """가장 최근 TOP 100 JSON 파일 찾기"""
    import re
    if not os.path.exists(OUTPUT_DIR):
        return None

    # top100_YYYYMMDD.json 형식만 매칭 (test, trend, strict 등 제외)
    pattern = re.compile(r'^top100_(\d{8})\.json$')
    files = []
    for f in os.listdir(OUTPUT_DIR):
        match = pattern.match(f)
        if match:
            files.append((match.group(1), f))  # (날짜, 파일명)

    if not files:
        return None

    # 날짜순 정렬 (내림차순)
    files.sort(reverse=True)
    return os.path.join(OUTPUT_DIR, files[0][1])


def get_top100_file_by_date(date_str: str) -> Optional[str]:
    """특정 날짜의 TOP 100 파일 찾기"""
    filename = f"top100_{date_str}.json"
    filepath = os.path.join(OUTPUT_DIR, filename)
    return filepath if os.path.exists(filepath) else None


@router.get("", response_model=Top100Response)
async def get_top100(
    date: Optional[str] = Query(None, description="조회 날짜 (YYYYMMDD), 미입력시 최신"),
    score_version: str = Query("v2", description="스코어 버전 (v1, v2, v3.5, v4, v5, v6, v7, v8)")
):
    """오늘의 AI 추천 TOP 100 (지정된 스코어 버전 기준, intraday CSV에서 읽음)"""
    import glob
    import pandas as pd

    # 유효한 스코어 버전 확인
    valid_versions = ['v1', 'v2', 'v3.5', 'v4', 'v5', 'v6', 'v7', 'v8']
    if score_version not in valid_versions:
        score_version = 'v5'

    # 장중 스코어 CSV에서 Top 100 조회
    intraday_dir = os.path.join(OUTPUT_DIR, 'intraday_scores')

    if date:
        # 특정 날짜의 마지막 CSV
        pattern = os.path.join(intraday_dir, f"{date}_*.csv")
        csv_files = sorted(glob.glob(pattern))
    else:
        # 최신 CSV
        csv_files = sorted(glob.glob(os.path.join(intraday_dir, "*.csv")))

    if not csv_files:
        raise HTTPException(status_code=404, detail="추천 데이터가 없습니다")

    latest_csv = csv_files[-1]

    try:
        df = pd.read_csv(latest_csv)
        df['code'] = df['code'].astype(str).str.zfill(6)
    except Exception as e:
        print(f"[TOP100 Error] {e}")
        raise HTTPException(status_code=500, detail="데이터 파일 읽기 중 오류가 발생했습니다")

    # 선택된 스코어 버전으로 정렬
    # CSV에서 v3.5는 'v3.5' 컬럼으로 저장됨
    score_col = score_version
    if score_col not in df.columns:
        # 컬럼이 없으면 v5로 폴백
        score_col = 'v5'
        if score_col not in df.columns:
            raise HTTPException(status_code=500, detail=f"{score_version} 점수 컬럼이 없습니다")

    df_sorted = df.sort_values(score_col, ascending=False).head(100)

    # 파일명에서 날짜 추출
    filename = os.path.basename(latest_csv)
    file_date = filename.split('_')[0]  # YYYYMMDD_HHMM.csv → YYYYMMDD

    # 장 시작 전 등락률 0 처리
    now = datetime.now()
    is_before_market = 7 <= now.hour < 9

    items = []
    for i, (_, row) in enumerate(df_sorted.iterrows(), 1):
        stock_code = row['code']
        score = int(row.get(score_col, 0))
        change_rate = 0.0 if is_before_market else round(float(row.get('change_pct', 0)), 2)
        current_price = int(row.get('close', 0))

        # 의견 계산
        if score >= 65:
            opinion = "매수"
        elif score >= 50:
            opinion = "관망"
        else:
            opinion = "매도"

        # signals 파싱
        signals_str = str(row.get('signals', ''))
        signals = [s.strip() for s in signals_str.split(',') if s.strip()]
        volume_surge = 'VOLUME_SURGE' in signals

        # 주의 시그널 체크
        if any(s in signals for s in ['OVERBOUGHT', 'DEATH_CROSS', 'BEARISH_DIVERGENCE']):
            opinion = "주의"

        items.append(Top100Item(
            rank=i,
            code=stock_code,
            name=row.get('name', ''),
            score=score,
            opinion=opinion,
            current_price=current_price,
            change_rate=change_rate,
            rsi=None,  # CSV에 RSI 없음
            macd_signal=None,  # CSV에 MACD 없음
            volume_surge=volume_surge
        ))

    return Top100Response(
        date=file_date,
        total_count=len(items),
        items=items
    )


@router.get("/intraday-score/{code}")
async def get_intraday_score(
    code: str,
    score_version: str = Query("v2", description="스코어 버전 (v1, v2, v3.5, v4, v5, v6, v7, v8)")
):
    """특정 종목의 장중 스코어 조회 (intraday CSV에서)"""
    import glob
    import pandas as pd

    # 유효한 스코어 버전 확인
    valid_versions = ['v1', 'v2', 'v3.5', 'v4', 'v5', 'v6', 'v7', 'v8']
    if score_version not in valid_versions:
        score_version = 'v5'

    # 종목 코드 6자리로 정규화
    code = code.zfill(6)

    # 장중 스코어 CSV에서 조회
    intraday_dir = os.path.join(OUTPUT_DIR, 'intraday_scores')
    csv_files = sorted(glob.glob(os.path.join(intraday_dir, "*.csv")))

    if not csv_files:
        # 장중 스코어 파일 없음 = 분석 대상 아님
        return {"code": code, "score": None, "in_target": False, "message": "장중 스코어 데이터 없음"}

    latest_csv = csv_files[-1]

    try:
        df = pd.read_csv(latest_csv)
        df['code'] = df['code'].astype(str).str.zfill(6)
    except Exception as e:
        print(f"[IntradayScore Error] {e}")
        return {"code": code, "score": None, "in_target": False, "message": "데이터 파일 읽기 오류"}

    # 스코어 컬럼 확인
    score_col = score_version
    if score_col not in df.columns:
        score_col = 'v5'
        if score_col not in df.columns:
            return {"code": code, "score": None, "in_target": False, "message": f"{score_version} 컬럼 없음"}

    # 종목 검색
    stock_row = df[df['code'] == code]

    if stock_row.empty:
        # 분석 대상 종목 아님 (896개에 포함 안됨)
        return {"code": code, "score": None, "in_target": False, "message": "분석 대상 종목 아님"}

    row = stock_row.iloc[0]
    score = int(row.get(score_col, 0))

    # signals 파싱
    signals_str = str(row.get('signals', ''))
    signals = [s.strip() for s in signals_str.split(',') if s.strip()]

    # 파일명에서 시간 추출
    filename = os.path.basename(latest_csv)
    file_time = filename.replace('.csv', '')  # YYYYMMDD_HHMM

    return {
        "code": code,
        "name": row.get('name', ''),
        "score": score,
        "score_version": score_version,
        "in_target": True,
        "signals": signals,
        "change_pct": round(float(row.get('change_pct', 0)), 2),
        "updated_at": file_time
    }


@router.get("/research-picks")
async def get_research_picks():
    """
    연구 기반 AI 추천 종목 (2026-02-05)

    학술 연구로 검증된 고승률 조건만 적용:
    - 거래량 폭발 (3x+): 78% 승률
    - 거래량 돌파 (2x+): 75% 승률
    - 갭다운 역전: 72% 승률
    """
    import glob
    import pandas as pd
    from trading.buy_sell_logic import should_buy_research_based
    from config import StrategyConfig as SC

    # 장중 스코어 CSV에서 조회
    intraday_dir = os.path.join(OUTPUT_DIR, 'intraday_scores')
    csv_files = sorted(glob.glob(os.path.join(intraday_dir, "*.csv")))

    if not csv_files:
        raise HTTPException(status_code=404, detail="추천 데이터가 없습니다")

    latest_csv = csv_files[-1]

    try:
        df = pd.read_csv(latest_csv)
        df['code'] = df['code'].astype(str).str.zfill(6)
    except Exception as e:
        print(f"[ResearchPicks Error] {e}")
        raise HTTPException(status_code=500, detail="데이터 파일 읽기 오류")

    # 파일명에서 시간 추출
    filename = os.path.basename(latest_csv)
    parts = filename.replace('.csv', '').split('_')
    file_date = parts[0]
    file_time = parts[1] if len(parts) > 1 else "0000"
    hour = int(file_time[:2]) if len(file_time) >= 2 else 12
    minute = int(file_time[2:4]) if len(file_time) >= 4 else 0

    # 장 시작 전 처리
    now = datetime.now()
    is_before_market = 7 <= now.hour < 9
    is_after_market = now.hour >= 16

    picks = []
    for _, row in df.iterrows():
        stock_code = row['code']
        scores = {
            'v1': int(row.get('v1', 50)),
            'v2': int(row.get('v2', 0)),
            'v4': int(row.get('v4', 0)),
            'v5': int(row.get('v5', 0)),
        }
        change_pct = float(row.get('change_pct', 0))
        volume_ratio = float(row.get('volume_ratio', 1.0))

        # signals 파싱
        signals_str = str(row.get('signals', ''))
        signals = [s.strip() for s in signals_str.split(',') if s.strip()]

        # 등락률 필터 (10% 초과 제외)
        if change_pct > SC.MAX_CHANGE_PCT:
            continue

        # 연구 기반 매수 조건 체크
        should_buy, reason = should_buy_research_based(
            scores, hour, minute, change_pct, volume_ratio, signals
        )

        if should_buy:
            # 전략 분류
            if "거래량폭발" in reason:
                strategy = "volume_explosion"
                win_rate = 78
            elif "거래량돌파" in reason:
                strategy = "volume_breakout"
                win_rate = 75
            elif "갭다운역전" in reason:
                strategy = "gap_reversal"
                win_rate = 72
            elif "ORB" in reason:
                strategy = "orb_breakout"
                win_rate = 70
            else:
                strategy = "score_based"
                win_rate = 65

            picks.append({
                "code": stock_code,
                "name": row.get('name', ''),
                "strategy": strategy,
                "win_rate": win_rate,
                "reason": reason,
                "scores": scores,
                "change_pct": round(change_pct, 2),
                "volume_ratio": round(volume_ratio, 1),
                "current_price": int(row.get('close', 0)),
                "signals": signals[:5],  # 최대 5개
            })

    # 승률 높은 순 + 거래량 높은 순 정렬
    picks.sort(key=lambda x: (-x['win_rate'], -x['volume_ratio']))

    return {
        "date": file_date,
        "time": f"{hour:02d}:{minute:02d}",
        "total_count": len(picks),
        "is_market_open": not is_before_market and not is_after_market,
        "strategy_summary": {
            "volume_explosion": len([p for p in picks if p['strategy'] == 'volume_explosion']),
            "volume_breakout": len([p for p in picks if p['strategy'] == 'volume_breakout']),
            "gap_reversal": len([p for p in picks if p['strategy'] == 'gap_reversal']),
            "orb_breakout": len([p for p in picks if p['strategy'] == 'orb_breakout']),
            "score_based": len([p for p in picks if p['strategy'] == 'score_based']),
        },
        "items": picks[:30]  # 상위 30개
    }


@router.get("/history", response_model=List[dict])
async def get_top100_history(
    days: int = Query(7, ge=1, le=30, description="조회 기간 (일)")
):
    """과거 TOP 100 이력"""
    if not os.path.exists(OUTPUT_DIR):
        return []

    files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith('top100_') and f.endswith('.json')]
    files.sort(reverse=True)

    history = []
    for filename in files[:days]:
        date_str = filename.replace('top100_', '').replace('.json', '')
        filepath = os.path.join(OUTPUT_DIR, filename)

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)

            # 데이터 형식 처리
            if isinstance(raw_data, dict):
                stocks_data = raw_data.get('stocks', [])
                total_count = raw_data.get('total_count', len(stocks_data))
            else:
                stocks_data = raw_data
                total_count = len(stocks_data)

            # 상위 5개만 포함
            top5 = []
            for i, stock in enumerate(stocks_data[:5], 1):
                top5.append({
                    'rank': i,
                    'code': stock.get('code', stock.get('종목코드', '')),
                    'name': stock.get('name', stock.get('종목명', '')),
                    'score': stock.get('score', stock.get('점수', 0))
                })

            history.append({
                'date': date_str,
                'total_count': total_count,
                'top5': top5
            })
        except:
            continue

    return history


@router.get("/stock/{code}")
async def get_stock_history(
    code: str,
    days: int = Query(30, ge=1, le=90, description="조회 기간 (일)")
):
    """특정 종목의 TOP 100 진입 이력"""
    if not os.path.exists(OUTPUT_DIR):
        return {"code": code, "history": []}

    files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith('top100_') and f.endswith('.json')]
    files.sort(reverse=True)

    history = []
    for filename in files[:days]:
        date_str = filename.replace('top100_', '').replace('.json', '')
        filepath = os.path.join(OUTPUT_DIR, filename)

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)

            # 데이터 형식 처리
            if isinstance(raw_data, dict):
                stocks_data = raw_data.get('stocks', [])
            else:
                stocks_data = raw_data

            for i, stock in enumerate(stocks_data, 1):
                stock_code = stock.get('code', stock.get('종목코드', ''))
                if stock_code == code:
                    history.append({
                        'date': date_str,
                        'rank': i,
                        'score': stock.get('score', stock.get('점수', 0)),
                        'opinion': stock.get('opinion', stock.get('의견', ''))
                    })
                    break
        except:
            continue

    return {
        "code": code,
        "appearances": len(history),
        "history": history
    }
