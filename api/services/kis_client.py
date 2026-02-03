"""
한국투자증권 API 클라이언트 (호환성 레이어)

실제 구현은 services/kis_client.py로 이동됨.
이 파일은 기존 import 호환성을 위해 유지됨.
"""

# Re-export from new location
from services.kis_client import KISClient, get_kis_client, get_kis_client_for_prices

__all__ = ['KISClient', 'get_kis_client', 'get_kis_client_for_prices']
