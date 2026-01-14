import { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { TrendingUp, BarChart3, Shield, Brain, Target, ExternalLink, Copy, Check } from 'lucide-react';

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

// 인앱 브라우저 감지
const isInAppBrowser = () => {
  const ua = navigator.userAgent || navigator.vendor || window.opera;
  // 카카오톡, 네이버, 라인, 페이스북, 인스타그램, 기타 인앱 브라우저 감지
  const inAppPatterns = [
    /KAKAOTALK/i,
    /NAVER/i,
    /LINE/i,
    /FBAN|FBAV/i,  // Facebook
    /Instagram/i,
    /Twitter/i,
    /Snapchat/i,
    /musical_ly/i,  // TikTok
    /BytedanceWebview/i,
    /DaumApps/i,
    /KAKAO/i,
  ];
  return inAppPatterns.some(pattern => pattern.test(ua));
};

export default function Login() {
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [isInApp, setIsInApp] = useState(false);
  const [copied, setCopied] = useState(false);
  const googleButtonRef = useRef(null);
  const { googleLogin } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    // 인앱 브라우저 감지
    setIsInApp(isInAppBrowser());

    if (GOOGLE_CLIENT_ID && !isInAppBrowser()) {
      const existingScript = document.querySelector('script[src="https://accounts.google.com/gsi/client"]');
      if (existingScript) {
        initializeGoogle();
        return;
      }

      const script = document.createElement('script');
      script.src = 'https://accounts.google.com/gsi/client';
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);

      script.onload = () => {
        initializeGoogle();
      };
    }
  }, []);

  const initializeGoogle = () => {
    if (window.google?.accounts?.id) {
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: handleGoogleCallback,
        ux_mode: 'popup',
        itp_support: true,
      });

      if (googleButtonRef.current) {
        window.google.accounts.id.renderButton(
          googleButtonRef.current,
          {
            type: 'standard',
            theme: 'filled_blue',
            size: 'large',
            width: 300,
            text: 'continue_with',
            logo_alignment: 'center',
          }
        );
      }
    }
  };

  const handleGoogleCallback = async (response) => {
    setError('');
    setLoading(true);

    try {
      await googleLogin(response.credential);
      navigate('/');
    } catch (err) {
      setError(err.response?.data?.detail || 'Google 로그인에 실패했습니다');
    } finally {
      setLoading(false);
    }
  };

  // URL 복사
  const copyUrl = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      // 클립보드 API 실패 시 대체 방법
      const textArea = document.createElement('textarea');
      textArea.value = window.location.href;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // 외부 브라우저로 열기 (Android intent)
  const openInBrowser = () => {
    const url = window.location.href;
    // Android intent 방식 시도
    window.location.href = `intent://${url.replace(/^https?:\/\//, '')}#Intent;scheme=https;package=com.android.chrome;end`;
  };

  const features = [
    { icon: Brain, text: 'AI 기반 종목 분석', color: 'text-purple-500' },
    { icon: Target, text: '실시간 매매 추천', color: 'text-red-500' },
    { icon: BarChart3, text: '기술적 지표 분석', color: 'text-blue-500' },
    { icon: Shield, text: '리스크 관리', color: 'text-green-500' },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-600 via-indigo-600 to-blue-700 flex flex-col">
      {/* 상단 장식 요소 */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none">
        <div className="absolute top-10 left-10 w-32 h-32 bg-white/10 rounded-full blur-2xl"></div>
        <div className="absolute top-40 right-5 w-24 h-24 bg-purple-400/20 rounded-full blur-xl"></div>
        <div className="absolute bottom-40 left-5 w-40 h-40 bg-blue-400/20 rounded-full blur-2xl"></div>
        <div className="absolute bottom-20 right-10 w-28 h-28 bg-indigo-400/20 rounded-full blur-xl"></div>
      </div>

      {/* 메인 컨텐츠 */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 relative z-10 pt-12">
        {/* 로고 아이콘 */}
        <div className="w-24 h-24 bg-white rounded-3xl shadow-2xl flex items-center justify-center mb-6 transform rotate-3 hover:rotate-0 transition-transform mt-4">
          <TrendingUp size={48} className="text-purple-600" />
        </div>

        {/* 타이틀 */}
        <h1 className="text-3xl font-bold text-white text-center mb-2">
          Kim's AI 주식분석
        </h1>
        <p className="text-white/80 text-center mb-6">
          인공지능 기반 스마트 투자 도우미
        </p>

        {/* 구글 로그인 버튼 - 제목 바로 아래 */}
        <div className="bg-white rounded-2xl px-6 py-4 mb-8 shadow-lg">
          {error && (
            <div className="bg-red-50 text-red-600 text-sm p-3 rounded-xl mb-4 text-center">
              {error}
            </div>
          )}

          {isInApp ? (
            // 인앱 브라우저 경고
            <div className="text-center">
              <div className="bg-amber-50 text-amber-700 text-sm p-3 rounded-xl mb-4">
                <p className="font-medium mb-1">외부 브라우저에서 열어주세요</p>
                <p className="text-xs text-amber-600">
                  카카오톡, 네이버 등 인앱 브라우저에서는<br />
                  Google 로그인이 지원되지 않습니다.
                </p>
              </div>
              <div className="flex flex-col gap-2">
                <button
                  onClick={openInBrowser}
                  className="w-full flex items-center justify-center gap-2 bg-purple-600 text-white py-3 px-4 rounded-xl font-medium hover:bg-purple-700 transition-colors"
                >
                  <ExternalLink size={18} />
                  Chrome으로 열기
                </button>
                <button
                  onClick={copyUrl}
                  className="w-full flex items-center justify-center gap-2 bg-gray-100 text-gray-700 py-3 px-4 rounded-xl font-medium hover:bg-gray-200 transition-colors"
                >
                  {copied ? <Check size={18} className="text-green-500" /> : <Copy size={18} />}
                  {copied ? '복사됨!' : 'URL 복사 후 브라우저에서 열기'}
                </button>
              </div>
            </div>
          ) : loading ? (
            <div className="flex justify-center py-2">
              <span className="loading loading-spinner loading-lg text-purple-600"></span>
            </div>
          ) : (
            <div
              ref={googleButtonRef}
              className="flex justify-center items-center"
              style={{ minHeight: '44px' }}
            />
          )}
        </div>

        {/* 차트 애니메이션 시각화 */}
        <div className="w-full max-w-xs bg-white/10 backdrop-blur-sm rounded-2xl p-6 mb-8">
          <div className="flex items-end justify-between h-24 gap-2">
            {[40, 65, 45, 80, 55, 90, 70, 95].map((height, i) => (
              <div
                key={i}
                className="flex-1 bg-gradient-to-t from-green-400 to-emerald-300 rounded-t-sm animate-pulse"
                style={{
                  height: `${height}%`,
                  animationDelay: `${i * 0.1}s`,
                  animationDuration: '2s',
                }}
              />
            ))}
          </div>
          <div className="flex justify-between mt-3 text-xs text-white/60">
            <span>분석</span>
            <span>예측</span>
            <span>추천</span>
          </div>
        </div>

        {/* 주요 기능 소개 */}
        <div className="w-full max-w-xs mb-8">
          <p className="text-white/50 text-xs text-center mb-3">주요 기능</p>
          <div className="grid grid-cols-2 gap-2">
            {features.map(({ icon: Icon, text, color }) => (
              <div
                key={text}
                className="bg-white/5 rounded-lg p-2.5 flex items-center gap-2 pointer-events-none"
              >
                <Icon size={16} className={`${color} opacity-70`} />
                <span className="text-white/70 text-xs">{text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 하단 면책 조항 */}
      <div className="bg-white/10 backdrop-blur-sm px-6 py-4 relative z-10">
        <p className="text-center text-xs text-white/60 leading-relaxed">
          로그인 시{' '}
          <Link to="/privacy" className="underline text-white/80">
            개인정보처리방침
          </Link>
          에 동의하게 됩니다.<br />
          본 서비스의 정보는 투자 권유가 아닙니다.
        </p>
      </div>
    </div>
  );
}
