import { useState, useEffect } from 'react';
import { AlertTriangle, X } from 'lucide-react';

export default function Disclaimer() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    // 처음 방문 시에만 표시 (localStorage 확인)
    const hasSeenDisclaimer = localStorage.getItem('disclaimerAccepted');
    if (!hasSeenDisclaimer) {
      setShow(true);
    }
  }, []);

  const handleAccept = () => {
    localStorage.setItem('disclaimerAccepted', 'true');
    setShow(false);
  };

  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl max-w-md w-full max-h-[80vh] overflow-y-auto">
        {/* 헤더 */}
        <div className="bg-amber-500 text-white p-4 rounded-t-2xl flex items-center gap-3">
          <AlertTriangle size={28} />
          <h2 className="text-lg font-bold">투자 유의사항</h2>
        </div>

        {/* 내용 */}
        <div className="p-5 space-y-4 text-sm text-gray-700">
          <p className="font-semibold text-base text-gray-900">
            본 서비스는 투자 참고 정보를 제공하며,
            투자 권유가 아닙니다.
          </p>

          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
            <p className="font-medium text-amber-800 mb-2">면책 조항</p>
            <ul className="space-y-2 text-amber-900">
              <li>• 본 앱에서 제공하는 정보는 투자의 참고 자료일 뿐이며, 투자 판단의 최종 책임은 이용자 본인에게 있습니다.</li>
              <li>• AI 분석 결과는 과거 데이터 기반의 기술적 분석이며, 미래 수익을 보장하지 않습니다.</li>
              <li>• 제공되는 정보의 정확성, 완전성을 보장하지 않으며, 이로 인한 손실에 대해 책임지지 않습니다.</li>
            </ul>
          </div>

          <div className="bg-gray-50 rounded-lg p-3">
            <p className="font-medium text-gray-800 mb-2">본 서비스는</p>
            <ul className="space-y-1 text-gray-600">
              <li>✓ 모든 이용자에게 동일한 정보를 제공합니다</li>
              <li>✓ 개인별 맞춤 투자 자문을 제공하지 않습니다</li>
              <li>✓ 수익률을 보장하거나 확정하지 않습니다</li>
            </ul>
          </div>

          <p className="text-xs text-gray-500">
            본 서비스 이용 시 위 사항에 동의한 것으로 간주됩니다.
          </p>
        </div>

        {/* 버튼 */}
        <div className="p-4 border-t">
          <button
            onClick={handleAccept}
            className="w-full bg-purple-600 text-white py-3 rounded-xl font-semibold hover:bg-purple-700 transition-colors"
          >
            확인했습니다
          </button>
        </div>
      </div>
    </div>
  );
}
