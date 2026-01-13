import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { TrendingUp, BarChart3, Shield, Zap, Brain, Target } from 'lucide-react';

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

export default function Login() {
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const googleButtonRef = useRef(null);
  const { googleLogin } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (GOOGLE_CLIENT_ID) {
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
        <p className="text-white/80 text-center mb-8">
          인공지능 기반 스마트 투자 도우미
        </p>

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

        {/* 기능 소개 */}
        <div className="grid grid-cols-2 gap-3 w-full max-w-xs mb-8">
          {features.map(({ icon: Icon, text, color }) => (
            <div
              key={text}
              className="bg-white/10 backdrop-blur-sm rounded-xl p-3 flex items-center gap-2"
            >
              <Icon size={20} className={color} />
              <span className="text-white text-xs font-medium">{text}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 하단 로그인 영역 */}
      <div className="bg-white rounded-t-3xl px-6 pt-8 pb-10 relative z-10">
        <p className="text-center text-gray-600 mb-4 font-medium">
          시작하기
        </p>

        {error && (
          <div className="bg-red-50 text-red-600 text-sm p-3 rounded-xl mb-4 text-center">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-4">
            <span className="loading loading-spinner loading-lg text-purple-600"></span>
          </div>
        ) : (
          <div
            ref={googleButtonRef}
            className="flex justify-center items-center"
            style={{ minHeight: '44px' }}
          />
        )}

        <p className="text-center text-xs text-gray-400 mt-6 leading-relaxed">
          로그인 시 서비스 이용약관에 동의하게 됩니다.<br />
          본 서비스의 정보는 투자 권유가 아닙니다.
        </p>
      </div>
    </div>
  );
}
