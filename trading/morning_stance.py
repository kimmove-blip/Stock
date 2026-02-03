"""
아침 시황 스탠스 연동 모듈

morning_briefing.py가 생성한 스탠스 파일을 읽어서
투자금액 배수를 반환합니다.
"""

import json
from datetime import datetime
from pathlib import Path


STANCE_FILE = Path("/home/kimhc/Stock/output/morning_stance.json")


def get_morning_stance_multiplier() -> tuple:
    """
    오늘의 투자 스탠스 배수를 반환

    Returns:
        (multiplier: float, stance: str, is_valid: bool)
        - multiplier: 투자금 배수 (0.3 ~ 1.2)
        - stance: 스탠스명 (공격적/적극적/중립/보수적/방어적/회피)
        - is_valid: 오늘 날짜의 유효한 스탠스인지 여부
    """
    try:
        if not STANCE_FILE.exists():
            return 1.0, "중립", False

        with open(STANCE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 오늘 날짜인지 확인
        stance_date = data.get("date", "")
        today = datetime.now().strftime('%Y-%m-%d')

        if stance_date != today:
            # 어제 스탠스 파일이면 기본값 반환
            return 1.0, "중립", False

        multiplier = data.get("multiplier", 1.0)
        stance = data.get("stance", "중립")

        return multiplier, stance, True

    except Exception as e:
        print(f"[WARN] 아침 스탠스 로드 실패: {e}")
        return 1.0, "중립", False


def get_morning_stance_info() -> dict:
    """
    오늘의 스탠스 상세 정보 반환
    """
    try:
        if not STANCE_FILE.exists():
            return {}

        with open(STANCE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)

    except Exception:
        return {}
