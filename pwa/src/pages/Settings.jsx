import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../contexts/AuthContext';
import {
  Mail,
  Moon,
  LogOut,
  ChevronRight,
  Shield,
  MessageCircle,
  Bell,
  BellRing,
  FileText,
  Trash2,
  UserX,
  RefreshCw,
} from 'lucide-react';
import { authAPI } from '../api/client';

export default function Settings() {
  const { user, logout, refreshUser } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [darkMode, setDarkMode] = useState(false);

  // 이메일 구독 토글
  const emailMutation = useMutation({
    mutationFn: (enabled) => authAPI.updateSettings({ email_subscription: enabled }),
    onSuccess: () => {
      refreshUser && refreshUser();
      queryClient.invalidateQueries(['user']);
    },
    onError: (error) => {
      alert(error.response?.data?.detail || '설정 변경에 실패했습니다');
    },
  });

  const handleLogout = () => {
    if (confirm('로그아웃 하시겠습니까?')) {
      logout();
      navigate('/login');
    }
  };

  const handleRefresh = async () => {
    if (confirm('앱을 최신 버전으로 업데이트합니다. 계속하시겠습니까?')) {
      try {
        // 서비스 워커 캐시 삭제
        if ('caches' in window) {
          const cacheNames = await caches.keys();
          await Promise.all(cacheNames.map(name => caches.delete(name)));
        }

        // 서비스 워커 업데이트
        if ('serviceWorker' in navigator) {
          const registrations = await navigator.serviceWorker.getRegistrations();
          for (const registration of registrations) {
            await registration.update();
          }
        }

        // React Query 캐시 초기화
        queryClient.clear();

        // 페이지 새로고침
        window.location.reload(true);
      } catch (error) {
        console.error('Refresh error:', error);
        window.location.reload(true);
      }
    }
  };

  // 개인정보 설정 메뉴 (관리자, 개인정보처리방침, 데이터삭제, 회원탈퇴)
  const privacyItems = [
    // 관리자만 보이도록
    ...(user?.is_admin ? [{
      icon: Shield,
      label: '관리자 페이지',
      action: () => navigate('/admin'),
    }] : []),
    {
      icon: FileText,
      label: '개인정보처리방침',
      action: () => navigate('/privacy'),
    },
    {
      icon: Trash2,
      label: '데이터 삭제',
      action: () => navigate('/delete-data'),
    },
    {
      icon: UserX,
      label: '회원 탈퇴',
      action: () => navigate('/delete-account'),
      danger: true,
    },
  ];

  return (
    <div className="max-w-md mx-auto">
      {/* 프로필 섹션 */}
      <div className="bg-white rounded-xl p-4 shadow-sm mb-4">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 bg-gradient-to-br from-purple-600 to-indigo-600 rounded-full flex items-center justify-center text-white text-2xl font-bold">
            {(user?.name || user?.username)?.charAt(0)?.toUpperCase() || 'U'}
          </div>
          <div>
            <h2 className="font-bold text-gray-800 text-lg">{user?.name || user?.username}</h2>
            <p className="text-gray-500 text-sm">{user?.email || '이메일 미등록'}</p>
          </div>
        </div>
      </div>

      {/* 알림 설정 섹션 */}
      <div className="bg-white rounded-xl shadow-sm mb-4">
        <div className="px-4 py-3 border-b border-gray-100">
          <h3 className="font-semibold text-gray-700 text-sm">알림 설정</h3>
        </div>

        {/* 푸시 알림 */}
        <button
          onClick={() => navigate('/push')}
          className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors border-b border-gray-100"
        >
          <div className="flex items-center gap-3">
            <Bell size={20} className="text-purple-500" />
            <div className="text-left">
              <span className="text-gray-700 block">푸시 알림</span>
              <span className="text-xs text-gray-400">하락/매도 신호 실시간 알림</span>
            </div>
          </div>
          <ChevronRight size={20} className="text-gray-400" />
        </button>

        {/* 알림 기록 */}
        <button
          onClick={() => navigate('/alerts')}
          className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors border-b border-gray-100"
        >
          <div className="flex items-center gap-3">
            <BellRing size={20} className="text-orange-500" />
            <div className="text-left">
              <span className="text-gray-700 block">알림 기록</span>
              <span className="text-xs text-gray-400">받은 알림 확인하기</span>
            </div>
          </div>
          <ChevronRight size={20} className="text-gray-400" />
        </button>

        {/* 텔레그램 알림 */}
        <button
          onClick={() => navigate('/telegram')}
          className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors border-b border-gray-100"
        >
          <div className="flex items-center gap-3">
            <MessageCircle size={20} className="text-blue-500" />
            <div className="text-left">
              <span className="text-gray-700 block">텔레그램 알림</span>
              <span className="text-xs text-gray-400">텔레그램으로 알림 받기</span>
            </div>
          </div>
          <ChevronRight size={20} className="text-gray-400" />
        </button>

        {/* TOP100 이메일 구독 */}
        <div className="flex items-center justify-between p-4">
          <div className="flex items-center gap-3">
            <Mail size={20} className="text-purple-500" />
            <div>
              <span className="text-gray-700 block">TOP100 이메일 구독</span>
              <span className="text-xs text-gray-400">매일 AI 추천 종목 리포트</span>
            </div>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={user?.email_subscription || false}
              onChange={(e) => emailMutation.mutate(e.target.checked)}
              disabled={emailMutation.isPending}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-600"></div>
          </label>
        </div>
      </div>

      {/* 앱 설정 */}
      <div className="bg-white rounded-xl shadow-sm mb-4">
        <div className="px-4 py-3 border-b border-gray-100">
          <h3 className="font-semibold text-gray-700 text-sm">앱 설정</h3>
        </div>

        {/* 앱 새로고침 */}
        <button
          onClick={handleRefresh}
          className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors border-b border-gray-100"
        >
          <div className="flex items-center gap-3">
            <RefreshCw size={20} className="text-green-500" />
            <div className="text-left">
              <span className="text-gray-700 block">앱 새로고침</span>
              <span className="text-xs text-gray-400">캐시 삭제 및 최신 버전 업데이트</span>
            </div>
          </div>
          <ChevronRight size={20} className="text-gray-400" />
        </button>

        <div className="flex items-center justify-between p-4">
          <div className="flex items-center gap-3">
            <Moon size={20} className="text-gray-500" />
            <span className="text-gray-700">다크 모드</span>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={darkMode}
              onChange={(e) => setDarkMode(e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-600"></div>
          </label>
        </div>
      </div>

      {/* 개인정보 설정 */}
      <div className="bg-white rounded-xl shadow-sm mb-4">
        <div className="px-4 py-3 border-b border-gray-100">
          <h3 className="font-semibold text-gray-700 text-sm">개인정보 설정</h3>
        </div>
        {privacyItems.map(({ icon: Icon, label, action, danger }, idx) => (
          <button
            key={label}
            onClick={action}
            className={`w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors ${
              idx < privacyItems.length - 1 ? 'border-b border-gray-100' : ''
            }`}
          >
            <div className="flex items-center gap-3">
              <Icon size={20} className={danger ? 'text-red-500' : 'text-gray-500'} />
              <span className={danger ? 'text-red-500' : 'text-gray-700'}>{label}</span>
            </div>
            <ChevronRight size={20} className="text-gray-400" />
          </button>
        ))}
      </div>

      {/* 로그아웃 */}
      <button
        onClick={handleLogout}
        className="w-full bg-white rounded-xl p-4 shadow-sm flex items-center gap-3 text-red-500 hover:bg-red-50 transition-colors"
      >
        <LogOut size={20} />
        <span>로그아웃</span>
      </button>

      {/* 버전 정보 */}
      <div className="text-center py-6 text-sm text-gray-400">
        <p>버전 1.0.0</p>
      </div>
    </div>
  );
}
