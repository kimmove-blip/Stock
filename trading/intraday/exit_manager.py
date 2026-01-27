"""
청산 관리 모듈
모든 보유 포지션의 청산 조건 평가 및 실행
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
from .position_manager import PositionManager


class ExitManager:
    """청산 조건 평가 및 관리"""

    # 청산 사유 코드
    EXIT_TARGET = "TARGET"      # 목표가 도달
    EXIT_STOP = "STOP"          # 손절가 도달
    EXIT_TRAILING = "TRAILING"  # 트레일링 스탑
    EXIT_TIME = "TIME"          # 시간 손절
    EXIT_SCORE = "SCORE"        # 스코어 하락
    EXIT_MANUAL = "MANUAL"      # 수동 청산

    def __init__(self, position_manager: PositionManager = None):
        """
        Args:
            position_manager: 포지션 매니저 (없으면 새로 생성)
        """
        self.pm = position_manager or PositionManager()

    def check_exit_condition(
        self,
        position: Dict,
        current_price: int,
        current_score: int = None
    ) -> Tuple[bool, Optional[str]]:
        """
        단일 포지션 청산 조건 체크

        Args:
            position: 포지션 정보
            current_price: 현재가
            current_score: 현재 스코어 (선택)

        Returns:
            (청산 여부, 청산 사유)
        """
        entry_price = position['entry_price']
        target_price = position['target_price']
        stop_price = position['stop_price']
        trailing_stop = position['trailing_stop_price']
        max_hold_until = position.get('max_hold_until')

        # 1. 목표가 도달
        if target_price and current_price >= target_price:
            return True, self.EXIT_TARGET

        # 2. 손절가 도달
        if stop_price and current_price <= stop_price:
            return True, self.EXIT_STOP

        # 3. 트레일링 스탑 도달
        if trailing_stop and current_price <= trailing_stop:
            return True, self.EXIT_TRAILING

        # 4. 시간 손절
        if max_hold_until:
            try:
                max_hold_dt = datetime.fromisoformat(max_hold_until)
                if datetime.now() >= max_hold_dt:
                    return True, self.EXIT_TIME
            except ValueError:
                pass

        # 5. 스코어 하락 (선택적)
        if current_score is not None:
            entry_score = position.get('entry_score', 0)
            # 스코어가 진입 시점 대비 30점 이상 하락
            if entry_score > 0 and current_score < entry_score - 30:
                return True, self.EXIT_SCORE

        return False, None

    def check_all_positions(
        self,
        user_id: int,
        price_getter,
        score_getter=None
    ) -> List[Dict]:
        """
        모든 오픈 포지션 청산 조건 체크

        Args:
            user_id: 사용자 ID
            price_getter: 현재가 조회 함수 (stock_code -> price)
            score_getter: 스코어 조회 함수 (stock_code -> score, 선택)

        Returns:
            청산 대상 포지션 리스트
            [{'position': Dict, 'current_price': int, 'exit_reason': str}, ...]
        """
        positions = self.pm.get_open_positions(user_id)
        exit_list = []

        for pos in positions:
            stock_code = pos['stock_code']

            # 현재가 조회
            current_price = price_getter(stock_code)
            if current_price is None:
                continue

            # 트레일링 스탑 업데이트 (신고가 갱신 시)
            self.pm.update_trailing_stop(pos['id'], current_price)

            # 최신 포지션 정보 다시 로드 (트레일링 업데이트 반영)
            updated_pos = self.pm.get_position_by_code(user_id, stock_code)
            if updated_pos:
                pos = updated_pos

            # 스코어 조회 (선택)
            current_score = None
            if score_getter:
                current_score = score_getter(stock_code)

            # 청산 조건 체크
            should_exit, exit_reason = self.check_exit_condition(pos, current_price, current_score)

            if should_exit:
                exit_list.append({
                    'position': pos,
                    'current_price': current_price,
                    'exit_reason': exit_reason
                })

        return exit_list

    def execute_exits(
        self,
        exit_list: List[Dict],
        order_executor=None,
        dry_run: bool = False
    ) -> List[Dict]:
        """
        청산 실행

        Args:
            exit_list: 청산 대상 리스트 (check_all_positions 결과)
            order_executor: 주문 실행 함수 (stock_code, side, quantity, price) -> order_result
            dry_run: True면 실제 주문 없이 시뮬레이션

        Returns:
            청산 결과 리스트
        """
        results = []

        for item in exit_list:
            pos = item['position']
            current_price = item['current_price']
            exit_reason = item['exit_reason']

            result = {
                'position_id': pos['id'],
                'stock_code': pos['stock_code'],
                'stock_name': pos['stock_name'],
                'strategy': pos['strategy'],
                'entry_price': pos['entry_price'],
                'exit_price': current_price,
                'quantity': pos['quantity'],
                'exit_reason': exit_reason,
                'pnl_rate': (current_price - pos['entry_price']) / pos['entry_price'] * 100,
                'executed': False,
                'order_no': None
            }

            if dry_run:
                print(f"[DRY-RUN] 청산: {pos['stock_code']} {pos['stock_name']} "
                      f"@{current_price:,}원 ({exit_reason}) "
                      f"수익률: {result['pnl_rate']:.2f}%")
                result['executed'] = True
            elif order_executor:
                try:
                    order_result = order_executor(
                        pos['stock_code'],
                        'sell',
                        pos['quantity'],
                        0  # 시장가
                    )
                    if order_result and order_result.get('success'):
                        result['executed'] = True
                        result['order_no'] = order_result.get('order_no')

                        # DB에서 포지션 청산 처리
                        self.pm.close_position(
                            pos['id'],
                            current_price,
                            exit_reason
                        )
                except Exception as e:
                    result['error'] = str(e)

            results.append(result)

        return results

    def get_exit_summary(self, user_id: int, days: int = 7) -> Dict:
        """
        최근 청산 요약

        Args:
            user_id: 사용자 ID
            days: 조회 기간

        Returns:
            청산 통계
        """
        from datetime import timedelta

        since = (datetime.now() - timedelta(days=days)).isoformat()

        with self.pm._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    exit_reason,
                    COUNT(*) as count,
                    AVG(realized_pnl_rate) as avg_pnl_rate,
                    SUM(realized_pnl) as total_pnl
                FROM intraday_positions
                WHERE user_id = ? AND status = 'closed' AND exit_time >= ?
                GROUP BY exit_reason
            """, (user_id, since))

            rows = cursor.fetchall()

            summary = {
                'by_reason': {},
                'total_exits': 0,
                'total_pnl': 0
            }

            for row in rows:
                reason = row['exit_reason'] or 'UNKNOWN'
                summary['by_reason'][reason] = {
                    'count': row['count'],
                    'avg_pnl_rate': row['avg_pnl_rate'] or 0,
                    'total_pnl': row['total_pnl'] or 0
                }
                summary['total_exits'] += row['count']
                summary['total_pnl'] += row['total_pnl'] or 0

            return summary

    def force_close_all(
        self,
        user_id: int,
        price_getter,
        order_executor=None,
        dry_run: bool = False,
        reason: str = None
    ) -> List[Dict]:
        """
        모든 포지션 강제 청산 (장 마감 등)

        Args:
            user_id: 사용자 ID
            price_getter: 현재가 조회 함수
            order_executor: 주문 실행 함수
            dry_run: 시뮬레이션 모드
            reason: 청산 사유

        Returns:
            청산 결과 리스트
        """
        positions = self.pm.get_open_positions(user_id)
        exit_list = []

        for pos in positions:
            current_price = price_getter(pos['stock_code'])
            if current_price:
                exit_list.append({
                    'position': pos,
                    'current_price': current_price,
                    'exit_reason': reason or self.EXIT_MANUAL
                })

        return self.execute_exits(exit_list, order_executor, dry_run)


class ExitConditionChecker:
    """전략별 청산 조건 체커"""

    @staticmethod
    def check_v2_trend_exit(
        position: Dict,
        current_price: int,
        current_score: int = None,
        ma20_slope: float = None
    ) -> Tuple[bool, Optional[str]]:
        """
        V2 추세추종 전용 청산 조건

        Args:
            position: 포지션 정보
            current_price: 현재가
            current_score: V2 스코어
            ma20_slope: 20일 이평선 기울기

        Returns:
            (청산 여부, 청산 사유)
        """
        entry_price = position['entry_price']
        target_price = position['target_price']
        stop_price = position['stop_price']
        trailing_stop = position['trailing_stop_price']

        # 기본 조건
        if target_price and current_price >= target_price:
            return True, ExitManager.EXIT_TARGET

        if stop_price and current_price <= stop_price:
            return True, ExitManager.EXIT_STOP

        if trailing_stop and current_price <= trailing_stop:
            return True, ExitManager.EXIT_TRAILING

        # V2 전용: 추세 전환 감지 (MA20 기울기가 음수로 전환)
        if ma20_slope is not None and ma20_slope < -0.5:
            # 수익 구간에서만 추세 전환 청산
            if current_price > entry_price * 1.02:
                return True, "TREND_REVERSAL"

        # V2 스코어 급락
        if current_score is not None and current_score < 40:
            return True, ExitManager.EXIT_SCORE

        return False, None

    @staticmethod
    def check_v8_bounce_exit(
        position: Dict,
        current_price: int,
        current_score: int = None
    ) -> Tuple[bool, Optional[str]]:
        """
        V8 역발상반등 전용 청산 조건

        Args:
            position: 포지션 정보
            current_price: 현재가
            current_score: V8 스코어

        Returns:
            (청산 여부, 청산 사유)
        """
        entry_price = position['entry_price']
        target_price = position['target_price']
        stop_price = position['stop_price']

        # 목표가/손절가 (V8은 빠른 청산)
        if target_price and current_price >= target_price:
            return True, ExitManager.EXIT_TARGET

        if stop_price and current_price <= stop_price:
            return True, ExitManager.EXIT_STOP

        # V8은 반등 실패 시 빠르게 청산
        profit_rate = (current_price - entry_price) / entry_price * 100

        # 손실 -2% 이상이고 스코어 하락
        if profit_rate < -2 and current_score and current_score < 50:
            return True, "BOUNCE_FAILED"

        return False, None

    @staticmethod
    def check_v10_follower_exit(
        position: Dict,
        current_price: int,
        leader_change: float = None,
        catchup_gap: float = None
    ) -> Tuple[bool, Optional[str]]:
        """
        V10 대장주-종속주 전용 청산 조건

        Args:
            position: 포지션 정보
            current_price: 현재가
            leader_change: 대장주 현재 등락률
            catchup_gap: 캐치업 갭 (대장주와의 격차)

        Returns:
            (청산 여부, 청산 사유)
        """
        entry_price = position['entry_price']
        target_price = position['target_price']
        stop_price = position['stop_price']

        # 기본 조건
        if target_price and current_price >= target_price:
            return True, ExitManager.EXIT_TARGET

        if stop_price and current_price <= stop_price:
            return True, ExitManager.EXIT_STOP

        # V10 전용: 대장주 하락 시 빠른 청산
        if leader_change is not None and leader_change < 0:
            # 대장주가 음전환하면 캐치업 실패 가능성
            profit_rate = (current_price - entry_price) / entry_price * 100
            if profit_rate < 1:  # 아직 수익이 적으면
                return True, "LEADER_REVERSAL"

        # 캐치업 완료 (격차가 줄어들면)
        if catchup_gap is not None and catchup_gap < 0.5:
            return True, "CATCHUP_COMPLETE"

        return False, None


if __name__ == "__main__":
    # 테스트
    em = ExitManager()

    # 테스트 포지션
    test_position = {
        'id': 1,
        'stock_code': '005930',
        'stock_name': '삼성전자',
        'strategy': 'v2_trend',
        'entry_price': 60000,
        'target_price': 63000,
        'stop_price': 58000,
        'trailing_stop_price': None,
        'max_hold_until': None,
        'entry_score': 80
    }

    # 청산 조건 테스트
    print("=== 청산 조건 테스트 ===")

    # 목표가 도달
    should_exit, reason = em.check_exit_condition(test_position, 64000)
    print(f"현재가 64,000원: 청산={should_exit}, 사유={reason}")

    # 손절가 도달
    should_exit, reason = em.check_exit_condition(test_position, 57000)
    print(f"현재가 57,000원: 청산={should_exit}, 사유={reason}")

    # 유지
    should_exit, reason = em.check_exit_condition(test_position, 61000)
    print(f"현재가 61,000원: 청산={should_exit}, 사유={reason}")

    # 스코어 하락
    should_exit, reason = em.check_exit_condition(test_position, 61000, current_score=40)
    print(f"현재가 61,000원, 스코어 40: 청산={should_exit}, 사유={reason}")
