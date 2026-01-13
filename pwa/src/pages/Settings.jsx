import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../contexts/AuthContext';
import {
  Bell,
  Mail,
  Moon,
  LogOut,
  ChevronRight,
  User,
  Lock,
  Shield,
  MessageCircle,
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

  const settingsItems = [
    {
      icon: User,
      label: '프로필 수정',
      action: () => alert('준비 중입니다'),
    },
    {
      icon: Lock,
      label: '비밀번호 변경',
      action: () => alert('준비 중입니다'),
    },
    // 관리자만 보이도록
    ...(user?.is_admin ? [{
      icon: Shield,
      label: '문의 관리 (관리자)',
      action: () => navigate('/admin'),
    }] : []),
  ];

  return (
    <div className="max-w-md mx-auto">
      {/* 프로필 섹션 */}
      <div className="bg-white rounded-xl p-4 shadow-sm mb-4">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 bg-gradient-to-br from-purple-600 to-indigo-600 rounded-full flex items-center justify-center text-white text-2xl font-bold">
            {user?.username?.charAt(0)?.toUpperCase() || 'U'}
          </div>
          <div>
            <h2 className="font-bold text-gray-800 text-lg">{user?.username}</h2>
            <p className="text-gray-500 text-sm">{user?.email || '이메일 미등록'}</p>
          </div>
        </div>
      </div>

      {/* 설정 항목 */}
      <div className="bg-white rounded-xl shadow-sm mb-4">
        {settingsItems.map(({ icon: Icon, label, action }, idx) => (
          <button
            key={label}
            onClick={action}
            className={`w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors ${
              idx < settingsItems.length - 1 ? 'border-b border-gray-100' : ''
            }`}
          >
            <div className="flex items-center gap-3">
              <Icon size={20} className="text-gray-500" />
              <span className="text-gray-700">{label}</span>
            </div>
            <ChevronRight size={20} className="text-gray-400" />
          </button>
        ))}
      </div>

      {/* 알림 설정 섹션 */}
      <div className="bg-white rounded-xl shadow-sm mb-4">
        <div className="px-4 py-3 border-b border-gray-100">
          <h3 className="font-semibold text-gray-700 text-sm">알림 설정</h3>
        </div>

        {/* 텔레그램 알림 */}
        <button
          onClick={() => navigate('/telegram')}
          className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors border-b border-gray-100"
        >
          <div className="flex items-center gap-3">
            <MessageCircle size={20} className="text-blue-500" />
            <div className="text-left">
              <span className="text-gray-700 block">텔레그램 알림</span>
              <span className="text-xs text-gray-400">하락/매도 신호 실시간 알림</span>
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
