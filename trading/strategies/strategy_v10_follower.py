"""
V10 대장주-종속주 전략 (장중 자동매매용)
- 테마/섹터 내 대장주 상승 시 종속주 캐치업 매매
- 상관관계 기반 시차 활용
"""

import pandas as pd
from typing import Dict, List, Tuple, Optional
from .base_strategy import BaseStrategy


# 테마별 대장주-종속주 매핑 (scoring/score_v10_leader_follower.py에서 가져옴)
LEADER_FOLLOWER_MAP = {
    # 반도체
    '005930': ['000660', '042700', '403870', '357780', '058470'],  # 삼성전자 -> SK하이닉스, 한미반도체, HPSP, 원익홀딩스, 리노공업
    '000660': ['042700', '403870', '357780', '036930', '058470'],  # SK하이닉스 -> 한미반도체 외

    # 2차전지
    '373220': ['247540', '006400', '003670', '086520'],  # LG에너지솔루션 -> 에코프로, 삼성SDI, 포스코퓨처엠, 에코프로비엠
    '006400': ['247540', '003670', '086520', '012450'],  # 삼성SDI -> 에코프로, 포스코퓨처엠, 에코프로비엠, 한화에어로스페이스

    # 바이오
    '207940': ['068270', '326030', '145020'],  # 삼성바이오 -> 셀트리온, SK바이오팜, 휴젤
    '068270': ['326030', '145020', '196170'],  # 셀트리온 -> SK바이오팜, 휴젤, 알테오젠

    # 엔터
    '352820': ['041510', '122870', '035900'],  # 하이브 -> 에스엠, YG엔터, JYP엔터

    # 게임
    '259960': ['036570', '263750', '078340'],  # 크래프톤 -> 엔씨소프트, 펄어비스, 컴투스

    # 조선
    '009540': ['010620', '042660'],  # 한국조선해양 -> 현대미포조선, 한화오션

    # 항공/방산
    '012450': ['047810', '298040'],  # 한화에어로스페이스 -> 한국항공우주, 효성중공업
}

# 대장주 목록
LEADER_STOCKS = list(LEADER_FOLLOWER_MAP.keys())


class StrategyV10Follower(BaseStrategy):
    """V10 대장주-종속주 전략"""

    NAME = "V10 대장주-종속주"
    DESCRIPTION = "대장주 상승 시 종속주 캐치업 매매"
    SCORE_COLUMN = "v2"  # V10은 별도 스코어 없으므로 V2 참조
    VERSION = "1.0"

    DEFAULT_CONFIG = {
        'score_threshold': 50,  # V10은 스코어보다 대장주 움직임이 중요
        'max_positions': 3,
        'min_amount': 5_000_000_000,
        'leader_min_change': 3.0,       # 대장주 최소 상승률
        'follower_max_change': 1.5,     # 종속주 최대 상승률 (아직 덜 오른 것)
        'min_catchup_gap': 2.0,         # 최소 캐치업 갭 (%)
        'exit_rules': {
            'target_catchup_pct': 70,   # 캐치업 70% 달성 시 청산
            'stop_pct': -3.0,           # -3% 손절
            'time_stop_days': 3,
            'target_atr_mult': 1.0,
            'stop_atr_mult': 0.5
        }
    }

    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.leader_map = LEADER_FOLLOWER_MAP
        self.leader_stocks = LEADER_STOCKS

    def get_leader_changes(self, df: pd.DataFrame) -> Dict[str, float]:
        """
        대장주 등락률 조회

        Args:
            df: 스코어 DataFrame

        Returns:
            대장주 코드 -> 등락률 매핑
        """
        leader_changes = {}

        for code in self.leader_stocks:
            row = df[df['code'] == code]
            if not row.empty:
                leader_changes[code] = row.iloc[0].get('change_pct', 0)

        return leader_changes

    def find_catchup_opportunities(
        self,
        df: pd.DataFrame,
        leader_changes: Dict[str, float]
    ) -> List[Dict]:
        """
        캐치업 기회 종목 발굴

        Args:
            df: 스코어 DataFrame
            leader_changes: 대장주 등락률

        Returns:
            캐치업 기회 리스트
        """
        opportunities = []
        min_leader_change = self.config.get('leader_min_change', 3.0)
        max_follower_change = self.config.get('follower_max_change', 1.5)
        min_gap = self.config.get('min_catchup_gap', 2.0)

        for leader_code, leader_change in leader_changes.items():
            # 대장주가 충분히 상승했는지 체크
            if leader_change < min_leader_change:
                continue

            # 해당 대장주의 종속주들 체크
            follower_codes = self.leader_map.get(leader_code, [])

            for follower_code in follower_codes:
                follower_row = df[df['code'] == follower_code]
                if follower_row.empty:
                    continue

                follower_row = follower_row.iloc[0]
                follower_change = follower_row.get('change_pct', 0)
                follower_score = follower_row.get('v2', 0)

                # 종속주가 아직 덜 올랐는지 체크
                if follower_change > max_follower_change:
                    continue

                # 캐치업 갭 계산
                catchup_gap = leader_change - follower_change

                if catchup_gap >= min_gap:
                    opportunities.append({
                        'code': follower_code,
                        'name': follower_row.get('name', ''),
                        'price': follower_row.get('close', 0),
                        'change_pct': follower_change,
                        'score': int(follower_score),
                        'leader_code': leader_code,
                        'leader_change': leader_change,
                        'catchup_gap': catchup_gap,
                        'signals': follower_row.get('signals', '')
                    })

        # 캐치업 갭 큰 순서로 정렬
        opportunities.sort(key=lambda x: x['catchup_gap'], reverse=True)

        return opportunities

    def filter_candidates(self, df: pd.DataFrame, context: Dict = None) -> pd.DataFrame:
        """
        V10 전략 후보 필터링
        (캐치업 기회 기반)

        Args:
            df: 전체 스코어 DataFrame
            context: 대장주 등락률 포함 컨텍스트

        Returns:
            캐치업 기회 DataFrame
        """
        if df is None or df.empty:
            return pd.DataFrame()

        # 대장주 등락률 조회
        leader_changes = context.get('leader_changes') if context else None
        if leader_changes is None:
            leader_changes = self.get_leader_changes(df)

        # 캐치업 기회 발굴
        opportunities = self.find_catchup_opportunities(df, leader_changes)

        if not opportunities:
            return pd.DataFrame()

        # DataFrame으로 변환
        return pd.DataFrame(opportunities)

    def evaluate(self, row: pd.Series, context: Dict = None) -> Dict:
        """
        단일 종목 평가

        Args:
            row: 캐치업 기회 데이터 (find_catchup_opportunities 결과)
            context: 시장 컨텍스트

        Returns:
            평가 결과
        """
        catchup_gap = row.get('catchup_gap', 0)
        leader_change = row.get('leader_change', 0)
        score = row.get('score', 0)
        signals = row.get('signals', '')

        reasons = []
        confidence = 0.5

        # 1. 대장주 상승률 기반
        if leader_change >= 5.0:
            confidence += 0.2
            reasons.append(f"대장주 +{leader_change:.1f}%")
        elif leader_change >= 3.0:
            confidence += 0.1
            reasons.append(f"대장주 +{leader_change:.1f}%")

        # 2. 캐치업 갭 기반
        if catchup_gap >= 4.0:
            confidence += 0.2
            reasons.append(f"캐치업 갭 {catchup_gap:.1f}%")
        elif catchup_gap >= 2.0:
            confidence += 0.1
            reasons.append(f"캐치업 갭 {catchup_gap:.1f}%")

        # 3. 기술적 지지 (V2 스코어)
        if score >= 60:
            confidence += 0.1
            reasons.append("기술적 지지")

        # 4. 시그널 체크
        if 'MA_ALIGNED' in signals:
            confidence += 0.05
            reasons.append("이평선 정배열")

        if 'MACD_BULL' in signals:
            confidence += 0.05
            reasons.append("MACD 상승")

        # 5. RSI 과열 체크 (과열이면 감점)
        if 'RSI_OVERBOUGHT' in signals:
            confidence -= 0.1
            reasons.append("RSI 과열 (감점)")

        # 신뢰도 범위 제한
        confidence = max(0, min(confidence, 1.0))

        # 매수 결정
        signal = 'SKIP'
        if catchup_gap >= 2.0 and confidence >= 0.6:
            signal = 'BUY'
        elif catchup_gap >= 1.5 and confidence >= 0.5:
            signal = 'HOLD'

        return {
            'signal': signal,
            'score': int(score),
            'confidence': round(confidence, 2),
            'reasons': reasons,
            'catchup_gap': catchup_gap,
            'leader_change': leader_change
        }

    def get_entry_signals(
        self,
        df: pd.DataFrame,
        context: Dict = None
    ) -> List[Dict]:
        """
        매수 시그널 생성 (V10 전용)

        Args:
            df: 스코어 DataFrame
            context: 시장 컨텍스트

        Returns:
            매수 시그널 리스트
        """
        # 대장주 등락률 조회
        if context is None:
            context = {}

        if 'leader_changes' not in context:
            context['leader_changes'] = self.get_leader_changes(df)

        # 캐치업 후보 필터링
        candidates = self.filter_candidates(df, context)

        if candidates.empty:
            return []

        signals = []
        for _, row in candidates.iterrows():
            result = self.evaluate(row, context)

            if result.get('signal') == 'BUY':
                signals.append({
                    'code': row['code'],
                    'name': row.get('name', ''),
                    'price': row.get('price', 0),
                    'score': result.get('score', 0),
                    'confidence': result.get('confidence', 0),
                    'reasons': result.get('reasons', []),
                    'catchup_gap': row.get('catchup_gap', 0),
                    'leader_code': row.get('leader_code', ''),
                    'leader_change': row.get('leader_change', 0),
                    'strategy': self.NAME,
                    'strategy_version': self.VERSION
                })

        # 캐치업 갭/신뢰도 순 정렬
        signals.sort(key=lambda x: (x['catchup_gap'], x['confidence']), reverse=True)

        return signals[:self.max_positions]

    def get_exit_params(self, entry_price: int, atr: float = None) -> Dict:
        """V10 전용 청산 파라미터"""
        params = super().get_exit_params(entry_price, atr)

        rules = self.exit_rules

        # 캐치업 완료 비율 목표
        params['target_catchup_pct'] = rules.get('target_catchup_pct', 70)

        # 고정 손절 비율
        stop_pct = rules.get('stop_pct', -3.0)
        params['stop_price'] = int(entry_price * (1 + stop_pct / 100))

        # 트레일링 스탑 미사용 (빠른 청산)
        params['use_trailing'] = False

        return params

    def calculate_target_from_catchup(
        self,
        entry_price: int,
        catchup_gap: float,
        target_pct: float = 70
    ) -> int:
        """
        캐치업 기반 목표가 계산

        Args:
            entry_price: 진입가
            catchup_gap: 캐치업 갭 (%)
            target_pct: 캐치업 목표 달성률 (%)

        Returns:
            목표가
        """
        # 캐치업 갭의 target_pct% 회복을 목표
        expected_gain = catchup_gap * (target_pct / 100)
        return int(entry_price * (1 + expected_gain / 100))


if __name__ == "__main__":
    # 테스트
    import sys
    sys.path.insert(0, '/home/kimhc/Stock')

    from trading.intraday.score_monitor import ScoreMonitor

    monitor = ScoreMonitor()
    df = monitor.get_latest_scores()

    if df is not None:
        strategy = StrategyV10Follower()

        print(f"=== {strategy.NAME} 테스트 ===")
        print(f"대장주 최소 상승률: {strategy.config.get('leader_min_change')}%")
        print(f"최대 포지션: {strategy.max_positions}")

        # 대장주 상태 확인
        print("\n=== 대장주 등락률 ===")
        leader_changes = strategy.get_leader_changes(df)
        for code, change in sorted(leader_changes.items(), key=lambda x: x[1], reverse=True)[:5]:
            name_row = df[df['code'] == code]
            name = name_row.iloc[0]['name'] if not name_row.empty else ''
            print(f"  {code} {name:12s}: {change:+.2f}%")

        signals = strategy.get_entry_signals(df)

        print(f"\n=== 캐치업 매수 시그널 ({len(signals)}개) ===")
        for sig in signals[:5]:
            print(f"  {sig['code']} {sig['name']:12s} "
                  f"캐치업갭={sig['catchup_gap']:.1f}% 신뢰도={sig['confidence']:.2f} "
                  f"가격={sig['price']:,}원")
            print(f"    대장주: {sig['leader_code']} (+{sig['leader_change']:.1f}%)")
            print(f"    사유: {', '.join(sig['reasons'][:3])}")
