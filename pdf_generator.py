"""
PDF 생성 모듈
스크리닝 결과를 PDF로 변환 (초기버전 형식)
"""

import os
from datetime import datetime
from pathlib import Path
from weasyprint import HTML, CSS

# 폰트 경로
FONT_DIR = Path(__file__).parent / "fonts"
FONT_REGULAR = FONT_DIR / "NanumBarunpenR.ttf"
FONT_BOLD = FONT_DIR / "NanumBarunpenB.ttf"


def get_base_css():
    """기본 CSS 스타일 (한글 폰트 포함)"""
    # 로컬 TTF 폰트 파일 직접 참조 (TTC 문제 회피)
    font_regular = FONT_REGULAR.resolve().as_uri()
    font_bold = FONT_BOLD.resolve().as_uri()

    return f"""
    @font-face {{
        font-family: 'NanumBarunpen';
        src: url('{font_regular}') format('truetype');
        font-weight: normal;
        font-style: normal;
    }}

    @font-face {{
        font-family: 'NanumBarunpen';
        src: url('{font_bold}') format('truetype');
        font-weight: bold;
        font-style: normal;
    }}

    html, body, div, span, h1, h2, h3, h4, h5, h6, p, table, th, td, li, ul, ol {{
        font-family: 'NanumBarunpen', sans-serif !important;
    }}

    * {{
        font-family: 'NanumBarunpen', sans-serif !important;
    }}

    body {{
        font-family: 'NanumBarunpen', sans-serif;
        line-height: 1.6;
        color: #333;
        max-width: 100%;
        margin: 0;
        padding: 30px;
        font-size: 10pt;
    }}

    h1 {{
        font-family: 'NanumBarunpen', sans-serif;
        font-weight: bold;
        color: #1a365d;
        border-bottom: 3px solid #2c5282;
        padding-bottom: 10px;
        font-size: 24pt;
        margin-bottom: 15px;
    }}

    h2 {{
        font-family: 'NanumBarunpen', sans-serif;
        font-weight: bold;
        color: #2c5282;
        margin-top: 25px;
        font-size: 14pt;
        border-bottom: 2px solid #2c5282;
        padding-bottom: 5px;
    }}

    h3 {{
        font-family: 'NanumBarunpen', sans-serif;
        font-weight: bold;
        color: #2d3748;
        font-size: 12pt;
        margin-top: 20px;
        margin-bottom: 10px;
    }}

    .header-info {{
        font-size: 10pt;
        color: #4a5568;
        margin-bottom: 20px;
    }}

    .header-info strong {{
        color: #2c5282;
    }}

    table {{
        border-collapse: collapse;
        width: 100%;
        margin: 15px 0;
        font-size: 9pt;
    }}

    th, td {{
        border: 1px solid #cbd5e0;
        padding: 8px 10px;
        text-align: left;
    }}

    th {{
        background-color: #2c5282;
        color: white;
        font-weight: bold;
    }}

    tr:nth-child(even) {{
        background-color: #f7fafc;
    }}

    .summary-table {{
        width: 60%;
        margin: 15px 0;
    }}

    .summary-table td:first-child {{
        background-color: #edf2f7;
        font-weight: bold;
        width: 50%;
    }}

    .summary-table tr:last-child td {{
        color: #c53030;
        font-weight: bold;
    }}

    .stock-section {{
        margin: 20px 0;
        padding-bottom: 15px;
        border-bottom: 1px solid #e2e8f0;
    }}

    .stock-title {{
        font-size: 13pt;
        font-weight: bold;
        color: #1a365d;
        margin-bottom: 5px;
    }}

    .stock-summary {{
        font-size: 10pt;
        margin-bottom: 10px;
    }}

    .stock-summary .score {{
        color: #2c5282;
        font-weight: bold;
    }}

    .indicator-table {{
        width: 100%;
        margin: 10px 0;
    }}

    .indicator-table th {{
        background-color: #2c5282;
        text-align: center;
    }}

    .indicator-table td:first-child {{
        text-align: center;
        width: 25%;
    }}

    .indicator-table td:nth-child(2) {{
        text-align: center;
        width: 25%;
    }}

    .highlight {{
        color: #c53030;
        font-weight: bold;
    }}

    .highlight-blue {{
        color: #2c5282;
        font-weight: bold;
    }}

    .signals-section {{
        margin: 10px 0;
    }}

    .signals-section h4 {{
        font-size: 10pt;
        font-weight: bold;
        color: #2c5282;
        margin-bottom: 5px;
    }}

    .signals-list {{
        margin: 5px 0 0 20px;
        padding: 0;
    }}

    .signals-list li {{
        margin: 5px 0;
        line-height: 1.4;
    }}

    .remaining-table {{
        width: 100%;
        font-size: 8pt;
    }}

    .remaining-table th {{
        padding: 6px 8px;
    }}

    .remaining-table td {{
        padding: 5px 8px;
    }}

    .positive {{
        color: #c53030;
    }}

    .negative {{
        color: #2b6cb0;
    }}

    .footer {{
        margin-top: 30px;
        padding-top: 20px;
        border-top: 1px solid #e2e8f0;
        font-size: 9pt;
        color: #718096;
    }}

    .strategy-section {{
        margin: 15px 0;
    }}

    .strategy-section h4 {{
        font-size: 10pt;
        font-weight: bold;
        margin-bottom: 5px;
    }}

    .strategy-section ul {{
        margin: 5px 0 0 20px;
        padding: 0;
    }}

    .strategy-section li {{
        margin: 3px 0;
    }}

    .caution-list {{
        margin: 10px 0 0 20px;
    }}

    .caution-list li {{
        margin: 5px 0;
    }}

    @page {{
        size: A4;
        margin: 1.5cm;
        @bottom-center {{
            content: "Kim's AI - 무단 재배포 금지";
            font-size: 8pt;
            color: #999;
        }}
    }}

    .header-logo {{
        position: absolute;
        top: 15px;
        right: 30px;
        font-size: 10pt;
        font-weight: bold;
        color: #718096;
        letter-spacing: 1px;
    }}

    .watermark {{
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%) rotate(-45deg);
        font-size: 60pt;
        color: rgba(44, 82, 130, 0.05);
        z-index: -1;
        white-space: nowrap;
        pointer-events: none;
    }}
    """


def get_indicator_interpretation(indicator, value):
    """지표 값에 대한 해석 반환"""
    if indicator == "rsi":
        if value < 30:
            return "과매도 (반등 기대)"
        elif value < 40:
            return "저구간 (매수 기회)"
        elif value < 50:
            return "중립~상승 초입"
        elif value < 60:
            return "건강한 상승 구간"
        elif value < 70:
            return "상승 모멘텀 강함"
        else:
            return "과매수 근접"
    elif indicator == "adx":
        if value < 20:
            return "추세 약함"
        elif value < 25:
            return "추세 형성 중"
        elif value < 30:
            return "강한 추세"
        elif value < 40:
            return "매우 강한 추세"
        else:
            return "극강 추세"
    elif indicator == "mfi":
        if value < 20:
            return "과매도"
        elif value < 40:
            return "저구간 (매수 기회)"
        elif value < 60:
            return "자금 유입 중"
        elif value < 80:
            return "자금 유입 활발"
        else:
            return "과매수 (과열 주의)"
    elif indicator == "volume_ratio":
        if value < 1.2:
            return "평균"
        elif value < 1.5:
            return "평균 이상"
        elif value < 2.0:
            return "증가"
        elif value < 3.0:
            return "급증"
        elif value < 5.0:
            return "급격한 거래량 증가"
        else:
            return "폭발적"
    elif indicator == "cmf":
        if value > 0.2:
            return "강한 자금유입"
        elif value > 0:
            return "자금 유입"
        elif value > -0.2:
            return "자금 유출"
        else:
            return "강한 자금유출"
    elif indicator == "cci":
        if value < -100:
            return "과매도 탈출"
        elif value > 100:
            return "과매수"
        else:
            return "중립"
    return ""


def generate_signal_interpretation(signals, indicators):
    """발생 신호에 대한 해석 생성"""
    interpretations = []

    # 이평선 관련
    ma_signals = []
    if "MA_ALIGNED" in signals:
        ma_signals.append("이평선 정배열")
    if "GOLDEN_CROSS_5_20" in signals:
        ma_signals.append("골든크로스(5/20)")
    if "GOLDEN_CROSS_20_60" in signals:
        ma_signals.append("<span class='highlight'>골든크로스(20/60)</span>")
    if ma_signals:
        if "GOLDEN_CROSS_20_60" in signals:
            interpretations.append(f"{' + '.join(ma_signals)} → <span class='highlight'>중장기 추세 전환 (가장 강력한 신호)</span>")
        else:
            interpretations.append(f"{' + '.join(ma_signals)} → <span class='highlight'>상승 추세 확인</span>")

    # MACD 관련
    macd_signals = []
    if "MACD_GOLDEN_CROSS" in signals:
        macd_signals.append("MACD 골든크로스")
    if "MACD_HIST_POSITIVE" in signals:
        macd_signals.append("히스토그램 양전환")
    if "MACD_HIST_RISING" in signals:
        macd_signals.append("히스토그램 상승")
    if macd_signals:
        interpretations.append(f"{' + '.join(macd_signals)} → <span class='highlight'>매수 모멘텀</span>")

    # 스토캐스틱 관련
    if "STOCH_GOLDEN_OVERSOLD" in signals:
        interpretations.append("스토캐스틱 과매도 골든크로스 → <span class='highlight'>강력 매수 신호</span>")
    elif "STOCH_GOLDEN_CROSS" in signals:
        interpretations.append("스토캐스틱 골든크로스 → <span class='highlight'>단기 반등 신호</span>")

    # 거래량 관련
    vol_signals = []
    vol_ratio = indicators.get("volume_ratio", 0)
    if "VOLUME_SURGE" in signals:
        vol_signals.append(f"거래량 급증({vol_ratio:.0f}배+)")
    elif "VOLUME_HIGH" in signals:
        vol_signals.append("거래량 증가")
    if "OBV_ABOVE_MA" in signals or "OBV_RISING" in signals:
        vol_signals.append("OBV 상승")
    if "CMF_STRONG_INFLOW" in signals:
        vol_signals.append("강한 자금유입(CMF)")
    if vol_signals:
        adx = indicators.get("adx", 0)
        if adx > 25:
            interpretations.append(f"{' + '.join(vol_signals)} → <span class='highlight'>세력 매집 의심</span>")
        else:
            interpretations.append(f"{' + '.join(vol_signals)} → <span class='highlight'>매수세 유입</span>")

    # 슈퍼트렌드/PSAR/일목
    trend_signals = []
    if "SUPERTREND_BUY" in signals:
        trend_signals.append("<span class='highlight'>슈퍼트렌드 매수</span>")
    elif "SUPERTREND_UPTREND" in signals:
        trend_signals.append("슈퍼트렌드 상승")
    if "PSAR_BUY_SIGNAL" in signals:
        trend_signals.append("<span class='highlight'>PSAR 매수</span>")
    elif "PSAR_UPTREND" in signals:
        trend_signals.append("PSAR 상승")
    if "ICHIMOKU_ABOVE_CLOUD" in signals:
        trend_signals.append("구름대 위")
    if "ICHIMOKU_GOLDEN_CROSS" in signals:
        trend_signals.append("<span class='highlight'>일목 골든크로스</span>")
    if trend_signals:
        interpretations.append(f"{'/'.join(trend_signals)} → <span class='highlight'>다중 지표 상승 확인</span>")

    # 볼린저밴드
    if "BB_LOWER_BOUNCE" in signals:
        interpretations.append("<span class='highlight-blue'>볼린저 하단 반등</span> → 바닥 확인 후 상승")
    if "BB_UPPER_BREAK" in signals:
        interpretations.append("볼린저 상단 돌파 → 단기 과열, 눌림목 대기 권장")

    # RSI 관련
    rsi = indicators.get("rsi", 50)
    if "RSI_OVERSOLD" in signals:
        interpretations.append(f"RSI {rsi:.0f} (과매도) → <span class='highlight'>반등 기대</span>")
    elif rsi > 70:
        interpretations.append(f"RSI {rsi:.0f} (과매수) → 단기 조정 가능")
    elif rsi < 60 and rsi > 50:
        interpretations.append(f"RSI {rsi:.0f} (과열 아님) → 추가 상승 여력 충분")

    # MFI 과매수 주의
    mfi = indicators.get("mfi", 50)
    if mfi > 80:
        interpretations.append(f"MFI {mfi:.0f} (과매수) → 단기 과열 주의 필요")

    # CCI 관련
    if "CCI_OVERSOLD" in signals:
        interpretations.append("CCI 과매도 탈출 → <span class='highlight'>바닥 확인 후 반등</span>")

    # 데드크로스/자금유출 경고
    if "DEAD_CROSS_5_20" in signals:
        interpretations.append("<span class='negative'>데드크로스(5/20)</span> → 단기 하락 주의")
    if "CMF_STRONG_OUTFLOW" in signals:
        interpretations.append("<span class='negative'>강한 자금유출(CMF)</span> 감지 → 매도 압력 존재")

    return interpretations


def format_rank_change_html(rank_change):
    """순위 변동을 HTML로 포맷"""
    if rank_change is None:
        return '<span style="color: #38a169; font-weight: bold;">NEW</span>'
    elif rank_change > 0:
        return f'<span style="color: #c53030;">↑{rank_change}</span>'
    elif rank_change < 0:
        return f'<span style="color: #2b6cb0;">↓{abs(rank_change)}</span>'
    else:
        return '<span style="color: #718096;">-</span>'


def format_streak_html(streak):
    """연속 일수를 HTML로 포맷"""
    if streak >= 5:
        return f'<span style="color: #c53030; font-weight: bold;">{streak}일 🔥</span>'
    elif streak >= 3:
        return f'<span style="color: #dd6b20; font-weight: bold;">{streak}일 ⭐</span>'
    else:
        return f'{streak}일'


def create_detailed_html(results, stats=None, date_str=None):
    """상세 분석 결과를 HTML로 변환 (초기버전 형식)"""
    from config import get_signal_kr

    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 스크리닝 엔진 버전명
    version_names = {
        'v1': '종합 기술적 분석',
        'v2': '추세 추종 강화',
        'v3': '래치 전략',
        'v4': 'Hybrid Sniper'
    }

    # 기본 통계 (stats가 없으면 기본값 사용)
    if stats is None:
        stats = {
            "total_stocks": 2901,
            "liquidity_passed": len(results) * 10,
            "special_excluded": len(results) * 9,
            "valid_analyzed": len(results) * 8,
            "final_selected": len(results)
        }

    # 연속 출현 통계
    streak_stats = stats.get('streak_stats', {}) if stats else {}
    new_entries = streak_stats.get('new_entries', 0)
    continued = streak_stats.get('continued', 0)
    streak_5plus = streak_stats.get('streak_5plus', 0)

    # 요약 테이블 HTML
    summary_html = f"""
    <table class="summary-table">
        <tr><td>전체 종목 수</td><td>{stats.get('total_stocks', 2901):,}개</td></tr>
        <tr><td>유동성 필터 통과</td><td>{stats.get('liquidity_passed', 939):,}개</td></tr>
        <tr><td>특수종목 제외 후</td><td>{stats.get('special_excluded', 915):,}개</td></tr>
        <tr><td>유효 분석 완료</td><td>{stats.get('valid_analyzed', 890):,}개</td></tr>
        <tr><td>최종 선정</td><td>{len(results)}개</td></tr>
    </table>

    <h3>신뢰도 지표</h3>
    <table class="summary-table">
        <tr><td>신규 진입</td><td>{new_entries}개</td></tr>
        <tr><td>연속 유지</td><td><strong>{continued}개</strong></td></tr>
        <tr><td>5일 이상 연속</td><td><span style="color:#c53030; font-weight:bold;">{streak_5plus}개 🔥</span></td></tr>
    </table>
    """

    # 상위 20개 종목 상세 분석
    detailed_html = ""
    for i, r in enumerate(results[:20], 1):
        code = r["code"]
        name = r["name"]
        market = r["market"]
        score = r["score"]
        close = r.get("close", 0)
        change = r.get("change_pct", 0)
        change_sign = "+" if change >= 0 else ""

        # 연속 출현 및 순위 변동
        streak = r.get("streak", 1)
        rank_change = r.get("rank_change")
        rank_change_html = format_rank_change_html(rank_change)
        streak_html = format_streak_html(streak)

        signals = r.get("signals", [])
        indicators = r.get("indicators", {})

        # === 점수 분석 ===
        trend_score = r.get("trend_score", indicators.get("trend_score", 0)) or 0
        momentum_score = r.get("momentum_score", indicators.get("momentum_score", 0)) or 0
        volume_score = r.get("volume_score", indicators.get("volume_score", 0)) or 0
        pattern_score = r.get("pattern_score", indicators.get("pattern_score", 0)) or 0
        sma20_slope = r.get("sma20_slope", indicators.get("sma20_slope", 0))
        trading_value = r.get("trading_value_억", indicators.get("trading_value_억", 0))
        high_60d_pct = r.get("high_60d_pct", indicators.get("high_60d_pct", 0))
        ma_status = r.get("ma_status", indicators.get("ma_status", ""))
        selection_reasons = r.get("selection_reasons", [])

        # 스크리닝 엔진 버전에 따른 점수 테이블
        scoring_ver = stats.get('scoring_version', 'v2') if stats else 'v2'
        if scoring_ver == 'v4':
            # V4: 추세(30) + 수급(30) + 패턴(20) + 모멘텀(20)
            score_breakdown = f"""
            <table class="indicator-table">
                <tr><th colspan="3" style="text-align:center; background:#2c5282; color:white;">점수 분석 (총 {score}점) - V4 Hybrid Sniper</th></tr>
                <tr style="background:#e8f0fe;"><td><strong>추세 점수</strong></td><td style="text-align:right; font-weight:bold;">{trend_score}/30점</td><td>정배열, 20일선 기울기, 구름대, MACD</td></tr>
                <tr><td><strong>수급 점수</strong></td><td style="text-align:right; font-weight:bold;">{volume_score}/30점</td><td>거래량, 거래대금, 기관/외국인</td></tr>
                <tr style="background:#e8f0fe;"><td><strong>패턴 점수</strong></td><td style="text-align:right; font-weight:bold;">{pattern_score}/20점</td><td>VCP 패턴, OBV 다이버전스</td></tr>
                <tr><td><strong>모멘텀 점수</strong></td><td style="text-align:right; font-weight:bold;">{momentum_score}/20점</td><td>RSI, StochRSI, 60일 신고가</td></tr>
            </table>
            """
        else:
            # V1-V3: 추세(30) + 모멘텀(35) + 거래량(35)
            score_breakdown = f"""
            <table class="indicator-table">
                <tr><th colspan="3" style="text-align:center; background:#2c5282; color:white;">점수 분석 (총 {score}점)</th></tr>
                <tr style="background:#e8f0fe;"><td><strong>추세 점수</strong></td><td style="text-align:right; font-weight:bold;">{trend_score}/30점</td><td>이평선 정배열, 20일선 기울기</td></tr>
                <tr><td><strong>모멘텀 점수</strong></td><td style="text-align:right; font-weight:bold;">{momentum_score}/35점</td><td>RSI, 60일 신고가</td></tr>
                <tr style="background:#e8f0fe;"><td><strong>거래량 점수</strong></td><td style="text-align:right; font-weight:bold;">{volume_score}/35점</td><td>거래량/거래대금</td></tr>
            </table>
            """

        # 지표 테이블 생성
        indicator_rows = ""

        # 20일선 기울기 (변별력 강화 핵심)
        if sma20_slope:
            if sma20_slope > 3:
                interp = "🔥 급등 추세"
            elif sma20_slope > 1.5:
                interp = "📈 상승 추세"
            elif sma20_slope > 0.5:
                interp = "완만한 상승"
            else:
                interp = "횡보"
            highlight = " class='highlight'" if sma20_slope > 3 else ""
            indicator_rows += f"<tr><td>20일선 기울기</td><td{highlight}>{sma20_slope:.1f}%</td><td>{interp}</td></tr>"

        # RSI
        rsi = r.get("rsi", indicators.get("rsi"))
        if rsi:
            if 60 <= rsi <= 75:
                interp = "✅ 최적 구간 (Sweet Spot)"
            elif rsi > 80:
                interp = "⚡ 강세 지속"
            elif 50 <= rsi < 60:
                interp = "안정적 상승"
            elif rsi < 30:
                interp = "⚠️ 과매도"
            else:
                interp = "중립"
            highlight = " class='highlight'" if 60 <= rsi <= 75 else ""
            indicator_rows += f"<tr><td>RSI (14)</td><td{highlight}>{rsi:.1f}</td><td>{interp}</td></tr>"

        # 거래량 배율
        vol_ratio = r.get("volume_ratio", indicators.get("volume_ratio"))
        if vol_ratio:
            if vol_ratio >= 5:
                interp = "🔥 폭발적 거래량"
            elif vol_ratio >= 3:
                interp = "📈 3배 이상 급증"
            elif vol_ratio >= 2:
                interp = "높은 거래량"
            else:
                interp = "보통"
            highlight = " class='highlight'" if vol_ratio >= 3 else ""
            indicator_rows += f"<tr><td>거래량 비율</td><td{highlight}>{vol_ratio:.1f}배</td><td>{interp}</td></tr>"

        # 거래대금
        if trading_value:
            if trading_value >= 500:
                interp = "🔥 초대형 거래"
            elif trading_value >= 100:
                interp = "✅ 대형 거래"
            elif trading_value >= 30:
                interp = "보통"
            else:
                interp = "⚠️ 소형"
            highlight = " class='highlight'" if trading_value >= 100 else ""
            indicator_rows += f"<tr><td>거래대금</td><td{highlight}>{trading_value:.0f}억원</td><td>{interp}</td></tr>"

        # 60일 고가 대비
        if high_60d_pct is not None:
            if high_60d_pct >= 0:
                interp = "🔥 60일 신고가 돌파"
            elif high_60d_pct >= -3:
                interp = "📈 고가 근접"
            elif high_60d_pct >= -5:
                interp = "고가 접근 중"
            else:
                interp = f"고가 대비 {high_60d_pct:.1f}%"
            highlight = " class='highlight'" if high_60d_pct >= -3 else ""
            indicator_rows += f"<tr><td>60일 고가 대비</td><td{highlight}>{high_60d_pct:+.1f}%</td><td>{interp}</td></tr>"

        # 이평선 상태
        if ma_status:
            ma_text = {"aligned": "✅ 정배열", "partial": "일부 정배열", "reverse_aligned": "❌ 역배열"}.get(ma_status, ma_status)
            indicator_rows += f"<tr><td>이평선 상태</td><td>{ma_text}</td><td>5일 > 20일 > 60일</td></tr>"

        # 지표 테이블이 비어있으면 기본값
        if not indicator_rows:
            indicator_rows = f"""
            <tr><td>RSI</td><td>-</td><td>-</td></tr>
            <tr><td>거래량 배율</td><td>-</td><td>-</td></tr>
            """

        indicator_table = f"""
        {score_breakdown}
        <table class="indicator-table" style="margin-top:10px;">
            <tr><th>핵심 지표</th><th>값</th><th>해석</th></tr>
            {indicator_rows}
        </table>
        """

        # 선정 이유 추가
        if selection_reasons:
            reasons_html = "<div style='margin-top:8px; padding:8px; background:#f8f9fa; border-radius:4px;'>"
            reasons_html += "<strong>📌 선정 이유:</strong> " + ", ".join(selection_reasons[:5])
            reasons_html += "</div>"
            indicator_table += reasons_html

        # 발생 신호 해석
        signal_interpretations = generate_signal_interpretation(signals, indicators)
        signals_html = ""
        if signal_interpretations:
            signals_html = "<div class='signals-section'><h4>발생 신호</h4><ul class='signals-list'>"
            for interp in signal_interpretations:
                signals_html += f"<li>{interp}</li>"
            signals_html += "</ul></div>"

        # 종목 섹션
        detailed_html += f"""
        <div class="stock-section">
            <div class="stock-title">{i}위. {name} ({code}) - {market} | {rank_change_html} | 연속 {streak_html}</div>
            <div class="stock-summary">
                <span class="score">종합점수: {score}점</span> | 현재가: {close:,.0f}원 | 등락률: {change_sign}{change:.2f}%
            </div>
            <h4>선정 이유</h4>
            {indicator_table}
            {signals_html}
        </div>
        """

    # 나머지 종목 테이블 (21위~)
    remaining_html = ""
    if len(results) > 20:
        remaining_html = f"""
        <h2>나머지 종목 (21~{len(results)}위)</h2>
        <table class="remaining-table">
            <tr>
                <th>순위</th>
                <th>종목코드</th>
                <th>종목명</th>
                <th>변동</th>
                <th>연속</th>
                <th>시장</th>
                <th>점수</th>
                <th>현재가</th>
                <th>등락률</th>
            </tr>
        """
        for i, r in enumerate(results[20:], 21):
            change = r.get("change_pct", 0)
            change_class = "positive" if change >= 0 else "negative"
            change_sign = "+" if change >= 0 else ""
            rank_change_html = format_rank_change_html(r.get("rank_change"))
            streak_html = format_streak_html(r.get("streak", 1))
            remaining_html += f"""
            <tr>
                <td style="text-align:center;">{i}</td>
                <td style="text-align:center;">{r['code']}</td>
                <td>{r['name']}</td>
                <td style="text-align:center;">{rank_change_html}</td>
                <td style="text-align:center;">{streak_html}</td>
                <td style="text-align:center;">{r['market']}</td>
                <td style="text-align:center;">{r['score']}</td>
                <td style="text-align:right;">{r.get('close', 0):,.0f}</td>
                <td style="text-align:right;" class="{change_class}">{change_sign}{change:.2f}%</td>
            </tr>
            """
        remaining_html += "</table>"

    # 신호 해설 섹션
    signal_guide_html = """
    <h2>신호 해설</h2>

    <h3>강력 매수 신호</h3>
    <table>
        <tr><th>신호</th><th>의미</th></tr>
        <tr><td>골든크로스(20/60)</td><td>중장기 추세 전환, 가장 강력한 매수 신호</td></tr>
        <tr><td>MACD 골든크로스</td><td>모멘텀 전환, 상승 시작점</td></tr>
        <tr><td>슈퍼트렌드 매수</td><td>추세 추종 지표 매수 전환</td></tr>
        <tr><td>PSAR 매수</td><td>패러볼릭 SAR 매수 전환</td></tr>
        <tr><td>일목 골든크로스</td><td>전환선/기준선 교차, 중기 상승 신호</td></tr>
    </table>

    <h3>보조 매수 신호</h3>
    <table>
        <tr><th>신호</th><th>의미</th></tr>
        <tr><td>이평선 정배열</td><td>단기 > 중기 > 장기 이평선 배열</td></tr>
        <tr><td>거래량 급증</td><td>평균 대비 2배 이상, 세력 매집 가능성</td></tr>
        <tr><td>OBV 상승</td><td>누적 거래량 상승, 매수세 우위</td></tr>
        <tr><td>구름대 위</td><td>일목균형표 구름대 상단, 지지선 확보</td></tr>
        <tr><td>CMF 자금유입</td><td>Chaikin Money Flow 양수, 기관 매수</td></tr>
    </table>

    <h3>주의 신호</h3>
    <table>
        <tr><th>신호</th><th>의미</th></tr>
        <tr><td>볼린저 상단 돌파</td><td>단기 과열, 조정 가능</td></tr>
        <tr><td>RSI 과매수 (70+)</td><td>단기 고점 근접</td></tr>
        <tr><td>MFI 과매수 (80+)</td><td>자금 유입 과열</td></tr>
        <tr><td>CCI/Williams%R 과매수</td><td>추가 상승 제한적</td></tr>
    </table>
    """

    # 투자 전략 제안
    strategy_html = """
    <h2>투자 전략 제안</h2>
    <div class="strategy-section">
        <h4>적극 매수 고려 (점수 100점 + 과열 아님)</h4>
        <ul>
            <li>RSI 60 이하 + 강한 매수 신호 동시 발생 종목</li>
            <li>골든크로스(20/60) 발생 + 거래량 급증 종목</li>
        </ul>

        <h4>눌림목 대기 권장 (과열 상태)</h4>
        <ul>
            <li>당일 급등(+10% 이상) + 거래량 폭발 종목</li>
            <li>MFI 80+ 또는 RSI 70+ 과매수 구간 종목</li>
        </ul>

        <h4>신중 접근 (혼합 신호)</h4>
        <ul>
            <li>상승 구조 + 자금유출 혼재 종목</li>
            <li>정배열 유지 중 당일 하락 종목</li>
        </ul>
    </div>
    """

    # 사용된 지표 섹션
    indicators_html = """
    <h2>사용된 기술적 지표</h2>
    <table>
        <tr><th>카테고리</th><th>지표</th></tr>
        <tr><td>추세</td><td>SMA(5/20/60), MACD, ADX, Supertrend, PSAR, Ichimoku</td></tr>
        <tr><td>모멘텀</td><td>RSI, Stochastic, CCI, Williams %R, ROC</td></tr>
        <tr><td>거래량</td><td>OBV, MFI, CMF, 거래량 배율</td></tr>
        <tr><td>변동성</td><td>볼린저밴드, ATR</td></tr>
    </table>
    """

    # 주의사항
    caution_html = """
    <h2>주의사항</h2>
    <ol class="caution-list">
        <li><strong>기술적 분석의 한계:</strong> 본 분석은 과거 가격/거래량 데이터 기반이며, 기업 펀더멘털(실적, 재무)은 미반영</li>
        <li><strong>과열 종목 주의:</strong> 점수 100점이라도 과매수 지표 다수 발생 시 단기 조정 가능</li>
        <li><strong>분할 매수 권장:</strong> 한 번에 진입보다 2~3회 분할 매수로 리스크 관리</li>
        <li><strong>손절 기준 설정:</strong> 슈퍼트렌드/PSAR 하향 전환 시 손절 고려</li>
        <li><strong>시장 상황 고려:</strong> 전체 시장 하락 시 개별 종목도 영향 받음</li>
    </ol>
    """

    # 전체 HTML 조립
    scoring_ver = stats.get('scoring_version', 'v2').upper() if stats else 'V2'
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Kim's AI - 내일의 관심 종목 TOP 100 ({scoring_ver}) - {date_str}</title>
    </head>
    <body>
        <div class="watermark">Kim's AI</div>

        <div class="header-logo">Kim's AI</div>
        <h1>내일의 관심 종목 TOP 100 ({scoring_ver})</h1>

        <div style="background-color: #fff3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
            <strong>투자 유의사항</strong><br><br>
            본 자료는 기술적 분석에 기반한 참고 자료이며, 투자 권유가 아닙니다.<br>
            투자 판단에 따른 손익은 전적으로 투자자 본인에게 귀속됩니다.<br><br>
            <strong>본 자료의 무단 전재 및 재배포를 금지합니다.</strong>
        </div>

        <div class="header-info">
            <strong>생성일시:</strong> {date_str}<br>
            <strong>스크리닝 엔진:</strong> {stats.get('scoring_version', 'v2').upper()} ({version_names.get(stats.get('scoring_version', 'v2'), '')})<br>
            <strong>분석 모드:</strong> 기술적 분석 (18개 지표 + 캔들패턴)<br>
            <strong>분석 대상:</strong> KRX 전종목 (KOSPI + KOSDAQ)<br>
            <strong>필터 조건:</strong> 시가총액 300억~1조, 거래대금 3억 이상, 주가 1,000원 이상, 관리종목/투자경고 제외
        </div>

        <h2>요약</h2>
        {summary_html}

        <h2>상위 20개 종목 상세 분석</h2>
        {detailed_html}

        {remaining_html}

        {signal_guide_html}

        {strategy_html}

        {indicators_html}

        {caution_html}

        <div class="footer">
            <p style="text-align: center; font-weight: bold;">Generated by Kim's AI v1.0 | Screening Engine {stats.get('scoring_version', 'v2').upper()}</p>
            <p style="text-align: center;">분석일: {date_str.split()[0] if ' ' in date_str else date_str}</p>
            <p style="text-align: center; color: #c53030;"><strong>본 자료의 무단 전재 및 재배포를 금지합니다.</strong></p>
        </div>
    </body>
    </html>
    """

    return html


def generate_detailed_pdf(results, output_path, stats=None):
    """상세 분석 결과를 PDF로 저장"""
    import tempfile
    import shutil
    from weasyprint.text.fonts import FontConfiguration

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html_content = create_detailed_html(results, stats=stats, date_str=date_str)
    css = CSS(string=get_base_css())

    # 커스텀 fontconfig 설정으로 TTC 폰트 문제 우회
    fontconfig_dir = None
    original_fontconfig = os.environ.get('FONTCONFIG_PATH')

    try:
        # 임시 fontconfig 설정 생성 (TTF 폰트만 사용)
        fontconfig_dir = tempfile.mkdtemp(prefix='fontconfig_')
        fonts_conf = os.path.join(fontconfig_dir, 'fonts.conf')

        with open(fonts_conf, 'w') as f:
            f.write(f'''<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
    <dir>{FONT_DIR}</dir>
    <cachedir>{fontconfig_dir}/cache</cachedir>
    <match target="pattern">
        <edit name="family" mode="prepend" binding="strong">
            <string>NanumBarunpen</string>
        </edit>
    </match>
    <selectfont>
        <rejectfont>
            <glob>*.ttc</glob>
            <glob>*.TTC</glob>
        </rejectfont>
    </selectfont>
</fontconfig>''')

        # 환경변수 설정
        os.environ['FONTCONFIG_PATH'] = fontconfig_dir
        os.environ['FONTCONFIG_FILE'] = fonts_conf

        font_config = FontConfiguration()

        HTML(string=html_content).write_pdf(
            output_path,
            stylesheets=[css],
            font_config=font_config
        )
    finally:
        # 환경변수 복원
        if original_fontconfig:
            os.environ['FONTCONFIG_PATH'] = original_fontconfig
        elif 'FONTCONFIG_PATH' in os.environ:
            del os.environ['FONTCONFIG_PATH']
        if 'FONTCONFIG_FILE' in os.environ:
            del os.environ['FONTCONFIG_FILE']

        # 임시 디렉토리 삭제
        if fontconfig_dir and os.path.exists(fontconfig_dir):
            shutil.rmtree(fontconfig_dir, ignore_errors=True)

    return output_path


# 하위 호환성을 위한 별칭
def generate_top100_pdf(results, output_path):
    """TOP 100 결과를 PDF로 저장 (하위 호환)"""
    return generate_detailed_pdf(results, output_path)


if __name__ == "__main__":
    # 테스트
    test_results = [
        {
            "code": "005930",
            "name": "삼성전자",
            "market": "KOSPI",
            "score": 100,
            "close": 72000,
            "change_pct": 2.5,
            "volume": 15000000,
            "signals": ["MA_ALIGNED", "GOLDEN_CROSS_5_20", "MACD_GOLDEN_CROSS", "VOLUME_SURGE", "OBV_ABOVE_MA", "SUPERTREND_UPTREND", "ICHIMOKU_ABOVE_CLOUD"],
            "patterns": ["HAMMER"],
            "indicators": {
                "rsi": 58.3,
                "adx": 35.5,
                "mfi": 76.6,
                "volume_ratio": 2.42,
                "cmf": 0.25,
            }
        }
    ] * 25

    # 다양한 테스트 데이터
    for i, r in enumerate(test_results):
        r["code"] = f"{i+1:06d}"
        r["name"] = f"테스트종목{i+1}"
        r["score"] = max(30, 100 - i * 3)

    output_path = "/home/kimhc/Stock/output/test_report_new.pdf"
    generate_detailed_pdf(test_results, output_path)
    print(f"PDF 생성 완료: {output_path}")
