"""
분기보고서 자동 업데이트 스케줄러
- 매일 새벽 3시에 실행
- 새로 공시된 보고서만 업데이트
"""
import json
import logging
import glob
from datetime import datetime
from typing import List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from api.services.dart_service import DartService, get_db_connection

logger = logging.getLogger(__name__)

# 스케줄러 인스턴스
scheduler = AsyncIOScheduler()


def get_tracked_stocks() -> List[dict]:
    """
    업데이트 대상 종목 목록 조회
    - TOP100 종목
    - 포트폴리오에 있는 종목
    - 관심종목
    - 이미 펀더멘탈 데이터가 있는 종목
    """
    stocks = []
    seen_codes = set()

    def add_stock(code: str, name: str):
        if code and code not in seen_codes:
            seen_codes.add(code)
            stocks.append({'code': code, 'name': name})

    # TOP100 종목 (최신 파일에서)
    try:
        top100_files = sorted(glob.glob('/home/kimhc/Stock/output/top100_*.json'), reverse=True)
        if top100_files:
            with open(top100_files[0], 'r', encoding='utf-8') as f:
                top100_data = json.load(f)
                # {"stocks": [...]} 구조
                stocks_list = top100_data.get('stocks', []) if isinstance(top100_data, dict) else top100_data
                for item in stocks_list:
                    add_stock(item.get('code'), item.get('name'))
            logger.info(f"TOP100에서 {len(seen_codes)}개 종목 로드")
    except Exception as e:
        logger.error(f"TOP100 로드 실패: {e}")

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 포트폴리오 종목
        cursor.execute("""
            SELECT DISTINCT stock_code, stock_name FROM portfolios
            WHERE stock_code IS NOT NULL
        """)
        for row in cursor.fetchall():
            add_stock(row['stock_code'], row['stock_name'])

        # 관심종목
        cursor.execute("""
            SELECT DISTINCT stock_code, stock_name FROM watchlists
            WHERE stock_code IS NOT NULL
        """)
        for row in cursor.fetchall():
            add_stock(row['stock_code'], row['stock_name'])

        # 이미 펀더멘탈 데이터가 있는 종목
        cursor.execute("""
            SELECT DISTINCT stock_code, stock_name FROM fundamental_data
        """)
        for row in cursor.fetchall():
            add_stock(row['stock_code'], row['stock_name'])

    logger.info(f"총 {len(stocks)}개 종목 업데이트 대상")
    return stocks


async def update_fundamental_data():
    """
    모든 추적 종목의 펀더멘탈 데이터 업데이트
    새로 공시된 보고서만 가져옴
    """
    logger.info("=== 펀더멘탈 데이터 업데이트 시작 ===")
    start_time = datetime.now()

    stocks = get_tracked_stocks()
    logger.info(f"업데이트 대상: {len(stocks)}개 종목")

    if not stocks:
        logger.info("업데이트 대상 종목이 없습니다")
        return

    dart = DartService()
    updated_count = 0
    error_count = 0

    for stock in stocks:
        try:
            code = stock['code']
            name = stock.get('name', '')

            # 새 보고서만 가져오기 (이미 있는 건 스킵)
            dart.update_stock_reports(code, name)
            updated_count += 1

        except Exception as e:
            logger.error(f"업데이트 실패 ({stock['code']}): {e}")
            error_count += 1

    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info(f"=== 펀더멘탈 데이터 업데이트 완료 ===")
    logger.info(f"처리: {updated_count}개, 오류: {error_count}개, 소요시간: {elapsed:.1f}초")


def start_scheduler():
    """스케줄러 시작"""
    if scheduler.running:
        logger.info("스케줄러가 이미 실행 중입니다")
        return

    # 매일 새벽 3시에 실행
    scheduler.add_job(
        update_fundamental_data,
        CronTrigger(hour=3, minute=0),
        id='update_fundamental',
        name='펀더멘탈 데이터 업데이트',
        replace_existing=True,
    )

    # 매월 15일 새벽 4시에 전체 재검사 (분기보고서 공시 시점)
    scheduler.add_job(
        update_fundamental_data,
        CronTrigger(day=15, hour=4, minute=0),
        id='monthly_fundamental_check',
        name='월간 펀더멘탈 전체 검사',
        replace_existing=True,
    )

    scheduler.start()
    logger.info("펀더멘탈 업데이트 스케줄러 시작됨 (매일 03:00, 매월 15일 04:00)")


def stop_scheduler():
    """스케줄러 중지"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("스케줄러 중지됨")


async def run_update_now():
    """수동 업데이트 실행 (테스트/관리용)"""
    await update_fundamental_data()
