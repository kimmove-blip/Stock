import { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Bell, Trash2, AlertTriangle, TrendingDown, ChevronRight, X, FileText } from 'lucide-react';
import { alertsAPI } from '../api/client';
import Loading from '../components/Loading';

export default function AlertHistory() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState(null);

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

  const deleteMutation = useMutation({
    mutationFn: (id) => alertsAPI.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries(['alerts']);
    },
  });

  const handleDelete = (e, id) => {
    e.stopPropagation();
    deleteMutation.mutate(id);
  };

  const handleClear = () => {
    if (confirm('모든 알림 기록을 삭제하시겠습니까?')) {
      clearMutation.mutate();
    }
  };

  // 알림 타입별 아이콘 및 색상
  const getAlertStyle = (alertType, stockCode) => {
    // 리포트/제안 타입 (REPORT_ 또는 SUGGEST_로 시작)
    if (stockCode?.startsWith('REPORT') || stockCode?.startsWith('SUGGEST')) {
      return {
        icon: FileText,
        bgColor: 'bg-purple-100',
        textColor: 'text-purple-600',
        borderColor: 'border-purple-200',
        isReport: true,
      };
    }
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

  // 날짜 포맷 (서버에서 KST 시간으로 저장됨)
  const formatDate = (dateStr) => {
    // DB에서 "2026-01-23 13:06:06" 형식으로 오는데, 시간대 정보가 없음
    // 서버가 KST로 저장하므로 명시적으로 +09:00 붙여서 파싱
    const kstDateStr = dateStr.replace(' ', 'T') + '+09:00';
    const date = new Date(kstDateStr);
    const now = new Date();
    const diff = now - date;
    const diffDays = Math.floor(diff / (1000 * 60 * 60 * 24));

    // 미래 시간이거나 음수면 "방금 전"으로 표시 (UTC/KST 혼용 데이터 대응)
    if (diff < 0 || diffDays < 0) {
      return '방금 전';
    } else if (diffDays === 0) {
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
            const style = getAlertStyle(alert.alert_type, alert.stock_code);
            const Icon = style.icon;
            const isExpanded = expandedId === alert.id;

            const handleClick = () => {
              if (style.isReport) {
                // 리포트는 펼치기/접기
                setExpandedId(isExpanded ? null : alert.id);
              } else {
                // 일반 알림은 종목 상세로 이동
                navigate(`/stock/${alert.stock_code}`);
              }
            };

            return (
              <div
                key={alert.id || idx}
                onClick={handleClick}
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
                      {alert.stock_name || alert.stock_code}
                    </p>
                    {alert.message && (
                      <p className={`text-sm text-gray-600 mt-1 ${isExpanded ? 'whitespace-pre-wrap' : 'line-clamp-2'}`}>
                        {isExpanded
                          ? alert.message.replace(/<[^>]*>/g, '')
                          : alert.message.replace(/<[^>]*>/g, '').substring(0, 100)
                        }
                      </p>
                    )}
                    {style.isReport && (
                      <p className="text-xs text-purple-500 mt-2">
                        {isExpanded ? '▲ 접기' : '▼ 펼쳐서 보기'}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={(e) => handleDelete(e, alert.id)}
                    disabled={deleteMutation.isPending}
                    className="p-1 hover:bg-gray-100 rounded-full transition-colors flex-shrink-0"
                  >
                    <X size={18} className="text-gray-400 hover:text-red-500" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
