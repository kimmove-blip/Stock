import { useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Bell, Trash2, AlertTriangle, TrendingDown, ChevronRight } from 'lucide-react';
import { alertsAPI } from '../api/client';
import Loading from '../components/Loading';

export default function AlertHistory() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // 페이지 진입 시 알림을 읽음으로 표시
  useEffect(() => {
    localStorage.setItem('lastViewedAlerts', new Date().toISOString());
    // Layout의 알림 쿼리 갱신을 위해 invalidate
    queryClient.invalidateQueries(['alerts']);

    // 앱 아이콘 배지 제거
    if ('clearAppBadge' in navigator) {
      navigator.clearAppBadge().catch(() => {});
    }
  }, [queryClient]);

  const { data, isLoading, error } = useQuery({
    queryKey: ['alerts'],
    queryFn: () => alertsAPI.list(30).then((res) => res.data),
  });

  const clearMutation = useMutation({
    mutationFn: () => alertsAPI.clear(),
    onSuccess: () => {
      queryClient.invalidateQueries(['alerts']);
    },
  });

  const handleClear = () => {
    if (confirm('모든 알림 기록을 삭제하시겠습니까?')) {
      clearMutation.mutate();
    }
  };

  // 알림 타입별 아이콘 및 색상
  const getAlertStyle = (alertType) => {
    if (alertType.includes('하락') || alertType.includes('손실')) {
      return {
        icon: TrendingDown,
        bgColor: 'bg-red-100',
        textColor: 'text-red-600',
        borderColor: 'border-red-200',
      };
    }
    if (alertType.includes('주의')) {
      return {
        icon: AlertTriangle,
        bgColor: 'bg-yellow-100',
        textColor: 'text-yellow-600',
        borderColor: 'border-yellow-200',
      };
    }
    return {
      icon: Bell,
      bgColor: 'bg-blue-100',
      textColor: 'text-blue-600',
      borderColor: 'border-blue-200',
    };
  };

  // 날짜 포맷
  const formatDate = (dateStr) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now - date;
    const diffDays = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
      return `오늘 ${date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}`;
    } else if (diffDays === 1) {
      return `어제 ${date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}`;
    } else if (diffDays < 7) {
      return `${diffDays}일 전`;
    } else {
      return date.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' });
    }
  };

  if (isLoading) {
    return <Loading text="알림 기록 불러오는 중..." />;
  }

  if (error) {
    return (
      <div className="alert alert-error">
        <span>알림 기록을 불러올 수 없습니다</span>
      </div>
    );
  }

  const alerts = data?.items || [];

  return (
    <div className="max-w-md mx-auto">
      {/* 헤더 */}
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-xl font-bold">알림 기록</h2>
          <p className="text-sm text-base-content/60">
            최근 30일간 {alerts.length}개의 알림
          </p>
        </div>
        {alerts.length > 0 && (
          <button
            onClick={handleClear}
            disabled={clearMutation.isPending}
            className="btn btn-ghost btn-sm text-red-500"
          >
            <Trash2 size={16} />
            전체 삭제
          </button>
        )}
      </div>

      {/* 알림 리스트 */}
      {alerts.length === 0 ? (
        <div className="text-center py-20">
          <div className="w-16 h-16 mx-auto mb-4 bg-gray-100 rounded-full flex items-center justify-center">
            <Bell size={32} className="text-gray-400" />
          </div>
          <p className="text-gray-500">알림 기록이 없습니다</p>
          <p className="text-sm text-gray-400 mt-2">
            보유종목에 변동이 있으면 알림을 받게 됩니다
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {alerts.map((alert, idx) => {
            const style = getAlertStyle(alert.alert_type);
            const Icon = style.icon;

            return (
              <div
                key={idx}
                onClick={() => navigate(`/stock/${alert.stock_code}`)}
                className={`bg-white rounded-xl p-4 shadow-sm border ${style.borderColor} cursor-pointer hover:shadow-md transition-shadow`}
              >
                <div className="flex items-start gap-3">
                  <div className={`w-10 h-10 ${style.bgColor} rounded-full flex items-center justify-center flex-shrink-0`}>
                    <Icon size={20} className={style.textColor} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className={`text-xs font-medium ${style.textColor} ${style.bgColor} px-2 py-0.5 rounded`}>
                        {alert.alert_type}
                      </span>
                      <span className="text-xs text-gray-400">
                        {formatDate(alert.created_at)}
                      </span>
                    </div>
                    <p className="font-semibold text-gray-800 mt-1">
                      {alert.stock_code}
                    </p>
                    {alert.message && (
                      <p className="text-sm text-gray-600 mt-1 line-clamp-2">
                        {alert.message.replace(/<[^>]*>/g, '').substring(0, 100)}
                      </p>
                    )}
                  </div>
                  <ChevronRight size={20} className="text-gray-300 flex-shrink-0" />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
