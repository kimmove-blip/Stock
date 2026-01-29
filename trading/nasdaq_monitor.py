"""
나스닥 모니터링 모듈

나스닥 전일 등락률을 조회하고, 이에 따른 투자금액 조정계수를 계산합니다.

조정계수 매핑:
| 나스닥 등락률 | 조정계수 |
|--------------|---------|
| -3% 이하     | 0.3배   |
| -2% ~ -3%    | 0.5배   |
| -1% ~ -2%    | 0.7배   |
| -1% 이상     | 1.0배   |
"""

from datetime import datetime, timedelta
from typing import Tuple, Optional


def get_nasdaq_previous_change() -> Tuple[Optional[float], Optional[str]]:
    """
    나스닥 전일 등락률 조회

    Returns:
        (등락률(%), 날짜) 튜플. 실패 시 (None, None)
    """
    try:
        import FinanceDataReader as fdr

        # 최근 5영업일 데이터 조회 (휴일 대비)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=10)

        # 나스닥 종합지수 (IXIC)
        df = fdr.DataReader('IXIC', start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))

        if df is None or len(df) < 2:
            print(f"  [NASDAQ] 데이터 부족: {len(df) if df is not None else 0}일")
            return None, None

        # 가장 최근 2거래일
        df = df.tail(2)
        prev_close = df.iloc[0]['Close']
        last_close = df.iloc[1]['Close']

        # 등락률 계산
        change_rate = (last_close - prev_close) / prev_close * 100
        last_date = df.index[-1].strftime('%Y-%m-%d')

        return round(change_rate, 2), last_date

    except Exception as e:
        print(f"  [NASDAQ] 데이터 조회 실패: {e}")
        return None, None


def get_nasdaq_adjustment_multiplier(change_rate: float) -> float:
    """
    나스닥 등락률에 따른 투자금액 조정계수 반환

    Args:
        change_rate: 나스닥 전일 등락률 (%)

    Returns:
        조정계수 (0.3 ~ 1.0)

    조정계수 매핑:
        -3% 이하: 0.3배 (폭락장, 리스크 최소화)
        -2% ~ -3%: 0.5배 (급락장, 보수적)
        -1% ~ -2%: 0.7배 (약세장)
        -1% 이상: 1.0배 (정상/강세장)
    """
    if change_rate <= -3.0:
        return 0.3
    elif change_rate <= -2.0:
        return 0.5
    elif change_rate <= -1.0:
        return 0.7
    else:
        return 1.0


def get_adjusted_investment_amount(base_amount: int) -> Tuple[int, float, float]:
    """
    나스닥 연동 조정된 투자금액 계산

    Args:
        base_amount: 기본 종목당 투자금액 (원)

    Returns:
        (조정된 투자금액, 조정계수, 나스닥 등락률) 튜플
        나스닥 데이터 조회 실패 시 (base_amount, 1.0, 0.0)
    """
    change_rate, date = get_nasdaq_previous_change()

    if change_rate is None:
        print(f"  [NASDAQ] 조회 실패 → 조정계수 1.0 (기본값) 적용")
        return base_amount, 1.0, 0.0

    multiplier = get_nasdaq_adjustment_multiplier(change_rate)
    adjusted_amount = int(base_amount * multiplier)

    print(f"  [NASDAQ] {date} 등락률: {change_rate:+.2f}% → 조정계수: {multiplier}배")
    print(f"  [NASDAQ] 투자금액: {base_amount:,}원 × {multiplier} = {adjusted_amount:,}원")

    return adjusted_amount, multiplier, change_rate


if __name__ == "__main__":
    # 테스트
    print("=== 나스닥 모니터 테스트 ===\n")

    # 1. 나스닥 등락률 조회
    change_rate, date = get_nasdaq_previous_change()
    if change_rate is not None:
        print(f"나스닥 {date}: {change_rate:+.2f}%")
        print(f"조정계수: {get_nasdaq_adjustment_multiplier(change_rate)}배")

    print()

    # 2. 투자금액 조정 테스트
    base_amount = 200000
    adjusted, multiplier, rate = get_adjusted_investment_amount(base_amount)
    print(f"\n결과: {adjusted:,}원 (조정계수 {multiplier}, 나스닥 {rate:+.2f}%)")

    print("\n=== 조정계수 테이블 ===")
    test_rates = [-5.0, -3.5, -2.5, -1.5, -0.5, 0.5, 1.5]
    for rate in test_rates:
        mult = get_nasdaq_adjustment_multiplier(rate)
        print(f"  {rate:+.1f}% → {mult}배 → {int(base_amount * mult):,}원")
