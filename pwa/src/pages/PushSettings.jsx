import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Bell, Send, CheckCircle, AlertCircle, BellOff, Loader2 } from 'lucide-react';
import { pushAPI } from '../api/client';
import {
  isPushSupported,
  getNotificationPermission,
  subscribeToPush,
  unsubscribeFromPush,
  subscriptionToJSON,
} from '../utils/pushNotification';

export default function PushSettings() {
  const queryClient = useQueryClient();
  const [permissionStatus, setPermissionStatus] = useState(getNotificationPermission());
  const [isSubscribing, setIsSubscribing] = useState(false);

  // 지원 여부 확인
  const isSupported = isPushSupported();

  // 현재 설정 조회
  const { data: settings, isLoading } = useQuery({
    queryKey: ['push-settings'],
    queryFn: () => pushAPI.getSettings().then((res) => res.data),
    enabled: isSupported,
  });

  // 권한 상태 업데이트
  useEffect(() => {
    const checkPermission = () => {
      setPermissionStatus(getNotificationPermission());
    };

    // 권한 변경 감지
    if ('permissions' in navigator) {
      navigator.permissions.query({ name: 'notifications' }).then((status) => {
        status.onchange = checkPermission;
      }).catch(() => {});
    }

    checkPermission();
  }, []);

  // 푸시 구독 활성화
  const handleSubscribe = async () => {
    setIsSubscribing(true);
    try {
      const subscription = await subscribeToPush();
      if (subscription) {
        const subJSON = subscriptionToJSON(subscription);
        await pushAPI.subscribe(subJSON);
        queryClient.invalidateQueries(['push-settings']);
        alert('푸시 알림이 활성화되었습니다!');
      } else {
        const permission = getNotificationPermission();
        setPermissionStatus(permission);
        if (permission === 'denied') {
          alert('알림 권한이 차단되어 있습니다. 브라우저 설정에서 알림을 허용해주세요.');
        }
      }
    } catch (error) {
      console.error('구독 실패:', error);
      alert('푸시 알림 활성화에 실패했습니다.');
    } finally {
      setIsSubscribing(false);
    }
  };

  // 푸시 구독 비활성화
  const unsubscribeMutation = useMutation({
    mutationFn: async () => {
      await unsubscribeFromPush();
      return pushAPI.unsubscribe();
    },
    onSuccess: () => {
      queryClient.invalidateQueries(['push-settings']);
      alert('푸시 알림이 비활성화되었습니다.');
    },
    onError: (err) => {
      alert(err.response?.data?.detail || '비활성화 실패');
    },
  });

  // 테스트 알림
  const testMutation = useMutation({
    mutationFn: () => pushAPI.test(),
    onSuccess: () => alert('테스트 알림이 전송되었습니다!'),
    onError: (err) => alert(err.response?.data?.detail || '전송 실패'),
  });

  if (!isSupported) {
    return (
      <div className="max-w-md mx-auto">
        <div className="bg-red-50 rounded-xl p-6 text-center">
          <AlertCircle size={48} className="mx-auto mb-4 text-red-500" />
          <h2 className="font-bold text-lg text-red-700 mb-2">지원되지 않음</h2>
          <p className="text-red-600 text-sm">
            이 브라우저는 푸시 알림을 지원하지 않습니다.<br />
            최신 Chrome, Firefox, Safari를 사용해주세요.
          </p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex justify-center items-center py-20">
        <span className="loading loading-spinner loading-lg text-purple-600"></span>
      </div>
    );
  }

  const isEnabled = settings?.subscription_count > 0;

  return (
    <div className="max-w-md mx-auto">
      {/* 헤더 */}
      <div className="bg-gradient-to-r from-purple-500 to-pink-500 rounded-xl p-6 text-white mb-6">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-12 h-12 bg-white/20 rounded-full flex items-center justify-center">
            <Bell size={24} />
          </div>
          <div>
            <h2 className="font-bold text-lg">푸시 알림</h2>
            <p className="text-sm opacity-80">실시간 주식 알림 받기</p>
          </div>
        </div>
        <div className="flex items-center gap-2 bg-white/20 rounded-lg px-3 py-2">
          {isEnabled ? (
            <>
              <CheckCircle size={18} />
              <span className="text-sm">활성화됨</span>
            </>
          ) : (
            <>
              <BellOff size={18} />
              <span className="text-sm">비활성화됨</span>
            </>
          )}
        </div>
      </div>

      {/* 권한 차단 경고 */}
      {permissionStatus === 'denied' && (
        <div className="bg-red-50 rounded-xl p-4 mb-4">
          <div className="flex items-start gap-3">
            <AlertCircle size={20} className="text-red-500 mt-0.5" />
            <div>
              <h3 className="font-bold text-red-700">알림 권한 차단됨</h3>
              <p className="text-sm text-red-600 mt-1">
                브라우저 설정에서 이 사이트의 알림을 허용해주세요.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 비활성화 상태 */}
      {!isEnabled && (
        <div className="bg-white rounded-xl shadow-sm p-4 mb-4">
          <h3 className="font-bold text-gray-800 mb-4">푸시 알림 활성화</h3>
          <div className="text-center py-4">
            <p className="text-gray-600 mb-4">
              버튼을 클릭하면 브라우저 알림 권한을 요청합니다.<br />
              허용하면 실시간 알림을 받을 수 있습니다.
            </p>
            <button
              onClick={handleSubscribe}
              disabled={isSubscribing || permissionStatus === 'denied'}
              className="btn btn-primary gap-2"
            >
              {isSubscribing ? (
                <Loader2 size={18} className="animate-spin" />
              ) : (
                <Bell size={18} />
              )}
              알림 활성화하기
            </button>
          </div>
        </div>
      )}

      {/* 활성화 상태 */}
      {isEnabled && (
        <>
          <div className="bg-white rounded-xl shadow-sm p-4 mb-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-bold text-gray-800">알림 상태</h3>
                <p className="text-sm text-gray-500">
                  {settings?.subscription_count}개 기기에서 활성화됨
                </p>
              </div>
              <div className="badge badge-success">활성</div>
            </div>
          </div>

          <div className="bg-white rounded-xl shadow-sm p-4 mb-4">
            <button
              onClick={() => testMutation.mutate()}
              disabled={testMutation.isPending}
              className="btn btn-outline btn-primary w-full gap-2"
            >
              {testMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                <Send size={16} />
              )}
              테스트 알림 보내기
            </button>
          </div>

          <div className="bg-white rounded-xl shadow-sm p-4 mb-4">
            <button
              onClick={() => {
                if (confirm('푸시 알림을 비활성화하시겠습니까?')) {
                  unsubscribeMutation.mutate();
                }
              }}
              disabled={unsubscribeMutation.isPending}
              className="btn btn-outline btn-error w-full gap-2"
            >
              {unsubscribeMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                <BellOff size={16} />
              )}
              알림 비활성화
            </button>
          </div>
        </>
      )}

      {/* 알림 종류 */}
      <div className="bg-gray-50 rounded-xl p-4">
        <h3 className="font-bold text-gray-700 mb-3">받을 수 있는 알림</h3>
        <ul className="space-y-2 text-sm text-gray-600">
          <li>- 보유종목 손실률 -10% 이상</li>
          <li>- 매도 신호 감지 (데드크로스 등)</li>
          <li>- 하락 위험 징후 감지</li>
        </ul>
      </div>
    </div>
  );
}
