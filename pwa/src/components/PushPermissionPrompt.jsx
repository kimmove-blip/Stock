import { useState, useEffect } from 'react';
import { Bell, X } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { pushAPI } from '../api/client';
import {
  isPushSupported,
  getNotificationPermission,
  subscribeToPush,
  subscriptionToJSON,
} from '../utils/pushNotification';

const PROMPT_DISMISSED_KEY = 'push_prompt_dismissed';
const PROMPT_DISMISSED_DURATION = 7 * 24 * 60 * 60 * 1000; // 7일

export default function PushPermissionPrompt() {
  const { user } = useAuth();
  const [show, setShow] = useState(false);
  const [isSubscribing, setIsSubscribing] = useState(false);

  useEffect(() => {
    // 조건 체크
    const checkShouldShow = async () => {
      // 로그인한 사용자만
      if (!user) return;

      // 푸시 지원 확인
      if (!isPushSupported()) return;

      // 이미 권한이 허용/거부된 경우 표시 안함
      const permission = getNotificationPermission();
      if (permission !== 'default') return;

      // 이전에 닫은 적 있는지 확인
      const dismissed = localStorage.getItem(PROMPT_DISMISSED_KEY);
      if (dismissed) {
        const dismissedTime = parseInt(dismissed, 10);
        if (Date.now() - dismissedTime < PROMPT_DISMISSED_DURATION) {
          return; // 7일 이내에 닫았으면 표시 안함
        }
      }

      // 약간의 지연 후 표시 (앱 로드 직후가 아닌)
      setTimeout(() => setShow(true), 2000);
    };

    checkShouldShow();
  }, [user]);

  const handleAllow = async () => {
    setIsSubscribing(true);
    try {
      const subscription = await subscribeToPush();
      if (subscription) {
        const subJSON = subscriptionToJSON(subscription);
        await pushAPI.subscribe(subJSON);
      }
    } catch (error) {
      console.error('Push subscription failed:', error);
    } finally {
      setIsSubscribing(false);
      setShow(false);
    }
  };

  const handleDismiss = () => {
    localStorage.setItem(PROMPT_DISMISSED_KEY, Date.now().toString());
    setShow(false);
  };

  if (!show) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 bg-black/50">
      <div className="bg-white rounded-2xl shadow-xl max-w-sm w-full p-6 animate-slide-up">
        <div className="flex justify-between items-start mb-4">
          <div className="w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center">
            <Bell size={24} className="text-purple-600" />
          </div>
          <button
            onClick={handleDismiss}
            className="p-1 hover:bg-gray-100 rounded-full transition-colors"
          >
            <X size={20} className="text-gray-400" />
          </button>
        </div>

        <h2 className="text-lg font-bold text-gray-800 mb-2">
          알림을 받으시겠습니까?
        </h2>
        <p className="text-gray-600 text-sm mb-6">
          보유종목 하락, 매도 신호 등<br />
          중요한 정보를 실시간으로 알려드립니다.
        </p>

        <div className="space-y-2">
          <button
            onClick={handleAllow}
            disabled={isSubscribing}
            className="btn btn-primary w-full"
          >
            {isSubscribing ? (
              <span className="loading loading-spinner loading-sm"></span>
            ) : (
              '알림 받기'
            )}
          </button>
          <button
            onClick={handleDismiss}
            className="btn btn-ghost w-full text-gray-500"
          >
            나중에
          </button>
        </div>
      </div>

      <style>{`
        @keyframes slide-up {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        .animate-slide-up {
          animation: slide-up 0.3s ease-out;
        }
      `}</style>
    </div>
  );
}
