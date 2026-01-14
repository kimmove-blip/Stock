import { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { MessageCircle, Send, CheckCircle, AlertCircle, ExternalLink, Loader2, Unlink } from 'lucide-react';
import { telegramAPI } from '../api/client';

export default function TelegramSettings() {
  const queryClient = useQueryClient();
  const [verificationCode, setVerificationCode] = useState(null);
  const [botLink, setBotLink] = useState(null);
  const [isChecking, setIsChecking] = useState(false);
  const intervalRef = useRef(null);
  const mountedRef = useRef(true);

  // 현재 설정 조회
  const { data: settings, isLoading } = useQuery({
    queryKey: ['telegram-settings'],
    queryFn: () => telegramAPI.getSettings().then((res) => res.data),
  });

  // 컴포넌트 마운트/언마운트
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, []);

  // 인증 코드 생성
  const generateCodeMutation = useMutation({
    mutationFn: () => telegramAPI.generateCode(),
    onSuccess: (res) => {
      if (!mountedRef.current) return;
      setVerificationCode(res.data.code);
      setBotLink(res.data.bot_link);
      setIsChecking(true);

      // 3초마다 체크 시작
      intervalRef.current = setInterval(async () => {
        if (!mountedRef.current) {
          clearInterval(intervalRef.current);
          return;
        }
        try {
          const checkRes = await telegramAPI.checkVerification();
          if (checkRes.data.verified && mountedRef.current) {
            clearInterval(intervalRef.current);
            setIsChecking(false);
            setVerificationCode(null);
            setBotLink(null);
            queryClient.invalidateQueries(['telegram-settings']);
            alert('텔레그램 연동이 완료되었습니다!');
          }
        } catch (err) {
          console.error('Check failed:', err);
        }
      }, 3000);
    },
  });

  // 연동 해제
  const disconnectMutation = useMutation({
    mutationFn: () => telegramAPI.disconnect(),
    onSuccess: () => {
      queryClient.invalidateQueries(['telegram-settings']);
      alert('텔레그램 연동이 해제되었습니다');
    },
  });

  // 알림 토글
  const toggleMutation = useMutation({
    mutationFn: (enabled) => telegramAPI.updateSettings({ alerts_enabled: enabled }),
    onSuccess: () => queryClient.invalidateQueries(['telegram-settings']),
  });

  // 테스트 메시지
  const testMutation = useMutation({
    mutationFn: () => telegramAPI.test(),
    onSuccess: () => alert('테스트 메시지가 전송되었습니다'),
    onError: (err) => alert(err.response?.data?.detail || '전송 실패'),
  });

  const handleCancel = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
    }
    setIsChecking(false);
    setVerificationCode(null);
    setBotLink(null);
  };

  if (isLoading) {
    return (
      <div className="flex justify-center items-center py-20">
        <span className="loading loading-spinner loading-lg text-purple-600"></span>
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto">
      {/* 헤더 */}
      <div className="bg-gradient-to-r from-blue-500 to-cyan-500 rounded-xl p-6 text-white mb-6">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-12 h-12 bg-white/20 rounded-full flex items-center justify-center">
            <MessageCircle size={24} />
          </div>
          <div>
            <h2 className="font-bold text-lg">텔레그램 알림</h2>
            <p className="text-sm opacity-80">실시간 주식 알림 받기</p>
          </div>
        </div>
        <div className="flex items-center gap-2 bg-white/20 rounded-lg px-3 py-2">
          {settings?.is_verified ? (
            <>
              <CheckCircle size={18} />
              <span className="text-sm">연동됨</span>
            </>
          ) : (
            <>
              <AlertCircle size={18} />
              <span className="text-sm">연동 필요</span>
            </>
          )}
        </div>
      </div>

      {/* 미연동 상태 */}
      {!settings?.is_verified && (
        <div className="bg-white rounded-xl shadow-sm p-4 mb-4">
          <h3 className="font-bold text-gray-800 mb-4">텔레그램 연동하기</h3>

          {!verificationCode ? (
            <div className="text-center py-4">
              <p className="text-gray-600 mb-4">
                버튼을 클릭하면 텔레그램 봇이 열립니다.<br />
                봇에서 시작 버튼을 누르면 자동으로 연동됩니다.
              </p>
              <button
                onClick={() => generateCodeMutation.mutate()}
                disabled={generateCodeMutation.isPending}
                className="btn btn-primary gap-2"
              >
                {generateCodeMutation.isPending ? (
                  <span className="loading loading-spinner loading-sm"></span>
                ) : (
                  <MessageCircle size={18} />
                )}
                텔레그램 연동하기
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="bg-blue-50 rounded-lg p-4 text-center">
                <p className="text-sm text-gray-600 mb-2">인증 코드</p>
                <p className="text-2xl font-bold text-blue-600 tracking-wider">{verificationCode}</p>
              </div>

              <button
                onClick={() => window.open(botLink, '_blank')}
                className="btn btn-primary w-full gap-2"
              >
                <ExternalLink size={18} />
                텔레그램 봇 열기
              </button>

              {isChecking && (
                <div className="flex items-center justify-center gap-2 text-gray-500">
                  <Loader2 size={16} className="animate-spin" />
                  <span className="text-sm">연동 대기 중...</span>
                </div>
              )}

              <button onClick={handleCancel} className="btn btn-ghost btn-sm w-full">
                취소
              </button>
            </div>
          )}
        </div>
      )}

      {/* 연동됨 상태 */}
      {settings?.is_verified && (
        <>
          <div className="bg-white rounded-xl shadow-sm p-4 mb-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-bold text-gray-800">알림 받기</h3>
                <p className="text-sm text-gray-500">하락/매도 신호 알림</p>
              </div>
              <input
                type="checkbox"
                className="toggle toggle-primary"
                checked={settings?.alerts_enabled || false}
                onChange={(e) => toggleMutation.mutate(e.target.checked)}
              />
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
              테스트 메시지 보내기
            </button>
          </div>

          <div className="bg-white rounded-xl shadow-sm p-4 mb-4">
            <button
              onClick={() => {
                if (confirm('텔레그램 연동을 해제하시겠습니까?')) {
                  disconnectMutation.mutate();
                }
              }}
              disabled={disconnectMutation.isPending}
              className="btn btn-outline btn-error w-full gap-2"
            >
              {disconnectMutation.isPending ? (
                <span className="loading loading-spinner loading-xs"></span>
              ) : (
                <Unlink size={16} />
              )}
              연동 해제
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
