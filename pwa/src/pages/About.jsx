import { Smartphone, TrendingUp, Shield, Zap } from 'lucide-react';

export default function About() {
  const features = [
    {
      icon: Zap,
      title: 'AI 기반 분석',
      description: '인공지능이 실시간으로 종목을 분석하고 추천합니다.',
    },
    {
      icon: TrendingUp,
      title: '기술적 분석',
      description: 'RSI, MACD, 볼린저밴드 등 20가지 이상의 지표를 분석합니다.',
    },
    {
      icon: Shield,
      title: '리스크 관리',
      description: '포트폴리오 위험도를 분석하고 손절 타이밍을 알려드립니다.',
    },
    {
      icon: Smartphone,
      title: '모바일 최적화',
      description: '언제 어디서나 스마트폰으로 편리하게 사용하세요.',
    },
  ];

  return (
    <div className="max-w-md mx-auto">
      {/* 앱 아이콘 */}
      <div className="text-center py-6">
        <div className="w-20 h-20 bg-gradient-to-br from-purple-600 to-indigo-600 rounded-2xl mx-auto flex items-center justify-center mb-4 shadow-lg">
          <TrendingUp size={40} className="text-white" />
        </div>
        <p className="text-gray-500">버전 1.0.0</p>
      </div>

      {/* 기능 소개 */}
      <div className="space-y-4">
        {features.map(({ icon: Icon, title, description }) => (
          <div key={title} className="bg-white rounded-xl p-4 shadow-sm flex gap-4">
            <div className="w-12 h-12 bg-purple-100 rounded-xl flex items-center justify-center flex-shrink-0">
              <Icon size={24} className="text-purple-600" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-800">{title}</h3>
              <p className="text-sm text-gray-500 mt-1">{description}</p>
            </div>
          </div>
        ))}
      </div>

      {/* 투자 유의사항 */}
      <div className="mt-6 bg-amber-50 rounded-xl p-4">
        <h3 className="font-semibold text-amber-800 mb-2">투자 유의사항</h3>
        <ul className="text-sm text-amber-700 space-y-1 list-disc list-inside">
          <li>본 서비스의 정보는 투자 권유가 아닙니다.</li>
          <li>제공되는 분석 및 추천은 참고용으로만 활용하세요.</li>
          <li>투자에 대한 최종 판단과 책임은 투자자 본인에게 있습니다.</li>
          <li>과거 수익률이 미래 수익을 보장하지 않습니다.</li>
        </ul>
      </div>

      {/* 푸터 */}
      <div className="text-center py-8 text-sm text-gray-400">
        <p>Made with AI</p>
        <p className="mt-1">2026 Kim's Stock Analysis</p>
      </div>
    </div>
  );
}
