"""
백그라운드 스케줄러
30분마다 TOP100 스크리닝 실행 + 캐싱
"""

import asyncio
import threading
import subprocess
import sys
import os
import json
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time as dt_time
from pathlib import Path

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).parent.parent.parent

# 스케줄러 상태
_scheduler_task = None
_last_run = None
_is_running = False
_is_caching = False  # 캐싱 중복 방지 플래그


def is_market_hours() -> bool:
    """장 운영 시간인지 확인 (09:00 ~ 15:30)"""
    now = datetime.now()

    # 주말 제외
    if now.weekday() >= 5:  # 토, 일
        return False

    current_time = now.time()
    market_open = dt_time(9, 0)
    market_close = dt_time(15, 30)

    return market_open <= current_time <= market_close


def run_screening_sync():
    """스크리닝 동기 실행 (subprocess로)"""
    global _last_run, _is_running

    if _is_running:
        print("[스케줄러] 이미 실행 중, 건너뜀")
        return False

    _is_running = True

    try:
        print(f"[스케줄러] TOP100 스크리닝 시작: {datetime.now()}")

        # daily_top100.py를 subprocess로 실행
        script_path = PROJECT_ROOT / "daily_top100.py"
        venv_python = PROJECT_ROOT / "venv" / "bin" / "python"

        # venv python이 있으면 사용, 없으면 시스템 python
        python_path = str(venv_python) if venv_python.exists() else sys.executable

        result = subprocess.run(
            [python_path, str(script_path), "--top", "100"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=600  # 10분 타임아웃
        )

        if result.returncode == 0:
            _last_run = datetime.now()
            print(f"[스케줄러] 스크리닝 완료: {_last_run}")
            # 스크리닝 완료 후 TOP100 캐싱 실행
            threading.Thread(target=cache_top100_stocks, daemon=True).start()
            return True
        else:
            print(f"[스케줄러] 스크리닝 실패: {result.stderr[:500]}")
            return False

    except subprocess.TimeoutExpired:
        print("[스케줄러] 스크리닝 타임아웃 (10분 초과)")
        return False
    except Exception as e:
        print(f"[스케줄러] 오류: {e}")
        return False
    finally:
        _is_running = False


async def screening_loop(interval_minutes: int = 30):
    """비동기 스크리닝 루프"""
    global _scheduler_task

    print(f"[스케줄러] 시작됨 - {interval_minutes}분 간격")

    while True:
        try:
            # 장 운영 시간에만 실행
            if is_market_hours():
                # 별도 스레드에서 동기 실행 (blocking 방지)
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, run_screening_sync)
            else:
                print(f"[스케줄러] 장외 시간 - 대기 중 ({datetime.now()})")

            # 다음 실행까지 대기
            await asyncio.sleep(interval_minutes * 60)

        except asyncio.CancelledError:
            print("[스케줄러] 종료됨")
            break
        except Exception as e:
            print(f"[스케줄러] 루프 오류: {e}")
            await asyncio.sleep(60)  # 오류 시 1분 후 재시도


def start_scheduler(interval_minutes: int = 30):
    """스케줄러 시작 (별도 스레드에서)"""
    global _scheduler_task

    def run_async_scheduler():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(screening_loop(interval_minutes))

    thread = threading.Thread(target=run_async_scheduler, daemon=True)
    thread.start()
    print(f"[스케줄러] 백그라운드 스레드 시작 (간격: {interval_minutes}분)")


def stop_scheduler():
    """스케줄러 중지"""
    global _scheduler_task
    if _scheduler_task:
        _scheduler_task.cancel()
        _scheduler_task = None
        print("[스케줄러] 중지됨")


def get_scheduler_status():
    """스케줄러 상태 반환"""
    return {
        "is_running": _is_running,
        "last_run": _last_run.isoformat() if _last_run else None,
        "is_market_hours": is_market_hours()
    }


# 시작 시 한 번 실행 (옵션)
def run_initial_screening():
    """서버 시작 시 초기 스크리닝 (장 시간일 때만)"""
    if is_market_hours():
        threading.Thread(target=run_screening_sync, daemon=True).start()


def run_initial_caching():
    """서버 시작 시 TOP100 캐싱 (10초 딜레이 후)"""
    import time

    def delayed_cache():
        time.sleep(10)  # 서버 완전 시작 대기
        cache_top100_stocks()

    threading.Thread(target=delayed_cache, daemon=True).start()
    print("[캐싱] 서버 시작 후 10초 뒤 TOP100 캐싱 예약됨")


def cache_top100_stocks():
    """TOP100 종목 캐싱 (상세 + 분석)"""
    global _is_caching

    # 중복 실행 방지
    if _is_caching:
        print("[캐싱] 이미 캐싱 중, 건너뜀")
        return

    _is_caching = True

    try:
        print(f"[캐싱] TOP100 종목 캐싱 시작: {datetime.now()}")

        # 최신 TOP100 JSON 파일 찾기
        output_dir = PROJECT_ROOT / "output"
        json_files = sorted(output_dir.glob("top100_*.json"), reverse=True)

        if not json_files:
            print("[캐싱] TOP100 파일 없음")
            return

        with open(json_files[0]) as f:
            data = json.load(f)

        stocks = data.get('stocks', data.get('items', []))[:20]  # 상위 20개만
        codes = [s['code'] for s in stocks]

        print(f"[캐싱] {len(codes)}개 종목 캐싱 시작")

        API_BASE = "http://localhost:8000/api"
        success = 0

        def cache_stock(code):
            import time
            try:
                # 종목 상세 캐싱
                requests.get(f"{API_BASE}/stocks/{code}", timeout=60)
                time.sleep(0.5)  # 서버 부하 완화
                # AI 분석 캐싱
                requests.get(f"{API_BASE}/stocks/{code}/analysis", timeout=60)
                time.sleep(0.5)
                return True
            except:
                return False

        # 3개 동시 처리 (서버 부하 고려)
        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(cache_stock, codes))
            success = sum(results)

        print(f"[캐싱] 완료: {success}/{len(codes)} 종목 캐싱됨")

    except Exception as e:
        print(f"[캐싱] 오류: {e}")
    finally:
        _is_caching = False


def run_caching_only():
    """캐싱만 실행 (스크리닝 없이)"""
    threading.Thread(target=cache_top100_stocks, daemon=True).start()
