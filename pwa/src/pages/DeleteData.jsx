import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Trash2, Briefcase, Star, Bell, Mail, CheckCircle } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useQueryClient } from '@tanstack/react-query';

export default function DeleteData() {
  const navigate = useNavigate();
  const { token } = useAuth();
  const queryClient = useQueryClient();

  const [deleting, setDeleting] = useState({});
  const [deleted, setDeleted] = useState({});

  const handleDelete = async (type, endpoint, confirmMsg) => {
    if (!confirm(confirmMsg)) return;

    setDeleting(prev => ({ ...prev, [type]: true }));

    try {
      const response = await fetch(`/api/${endpoint}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        setDeleted(prev => ({ ...prev, [type]: true }));
        // 관련 캐시 무효화
        queryClient.invalidateQueries({ queryKey: [type] });
      } else {
        const data = await response.json();
        alert(data.detail || '삭제에 실패했습니다.');
      }
    } catch (error) {
      alert('삭제 중 오류가 발생했습니다.');
    } finally {
      setDeleting(prev => ({ ...prev, [type]: false }));
    }
  };

  const handleResetSetting = async (type, field) => {
    const confirmMsg = type === 'telegram'
      ? '텔레그램 연동을 해제하시겠습니까?'
      : '이메일 구독을 해제하시겠습니까?';

    if (!confirm(confirmMsg)) return;

    setDeleting(prev => ({ ...prev, [type]: true }));

    try {
      const endpoint = type === 'telegram' ? 'telegram/settings' : 'auth/settings';
      const body = type === 'telegram'
        ? { chat_id: '', enabled: false }
        : { email_subscription: false };

      const response = await fetch(`/api/${endpoint}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      });

      if (response.ok) {
        setDeleted(prev => ({ ...prev, [type]: true }));
      } else {
        const data = await response.json();
        alert(data.detail || '설정 변경에 실패했습니다.');
      }
    } catch (error) {
      alert('설정 변경 중 오류가 발생했습니다.');
    } finally {
      setDeleting(prev => ({ ...prev, [type]: false }));
    }
  };

  const dataOptions = [
    {
      type: 'portfolio',
      icon: Briefcase,
      title: '포트폴리오 전체 삭제',
      description: '등록된 모든 보유 종목 데이터를 삭제합니다.',
      action: () => handleDelete('portfolio', 'portfolio/clear', '포트폴리오의 모든 종목을 삭제하시겠습니까?'),
    },
    {
      type: 'watchlist',
      icon: Star,
      title: '관심종목 전체 삭제',
      description: '모든 카테고리의 관심종목을 삭제합니다.',
      action: () => handleDelete('watchlist', 'watchlist/clear', '모든 관심종목을 삭제하시겠습니까?'),
    },
    {
      type: 'alerts',
      icon: Bell,
      title: '알림 기록 삭제',
      description: '텔레그램 알림 발송 기록을 삭제합니다.',
      action: () => handleDelete('alerts', 'alerts/clear', '모든 알림 기록을 삭제하시겠습니까?'),
    },
    {
      type: 'telegram',
      icon: Bell,
      title: '텔레그램 연동 해제',
      description: '텔레그램 알림 설정을 초기화합니다.',
      action: () => handleResetSetting('telegram'),
    },
    {
      type: 'email',
      icon: Mail,
      title: '이메일 구독 해제',
      description: '일일 리포트 이메일 수신을 중단합니다.',
      action: () => handleResetSetting('email'),
    },
  ];

  return (
    <div className="pb-20">
      {/* 헤더 */}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate(-1)} className="btn btn-ghost btn-sm">
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-xl font-bold">데이터 삭제</h1>
      </div>

      {/* 안내 */}
      <div className="alert alert-info mb-6">
        <div>
          <p className="text-sm">
            계정은 유지하면서 특정 데이터만 삭제할 수 있습니다.
            삭제된 데이터는 복구할 수 없습니다.
          </p>
        </div>
      </div>

      {/* 삭제 옵션 목록 */}
      <div className="space-y-3">
        {dataOptions.map(({ type, icon: Icon, title, description, action }) => (
          <div key={type} className="card bg-base-100 shadow">
            <div className="card-body p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-base-200 rounded-lg">
                    <Icon size={20} className="text-base-content/70" />
                  </div>
                  <div>
                    <h3 className="font-medium">{title}</h3>
                    <p className="text-sm text-base-content/60">{description}</p>
                  </div>
                </div>

                {deleted[type] ? (
                  <div className="flex items-center gap-1 text-success">
                    <CheckCircle size={18} />
                    <span className="text-sm">완료</span>
                  </div>
                ) : (
                  <button
                    onClick={action}
                    disabled={deleting[type]}
                    className="btn btn-error btn-sm"
                  >
                    {deleting[type] ? (
                      <span className="loading loading-spinner loading-xs"></span>
                    ) : (
                      <Trash2 size={16} />
                    )}
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* 계정 삭제 링크 */}
      <div className="mt-8 pt-6 border-t border-base-300">
        <p className="text-center text-sm text-base-content/60 mb-3">
          모든 데이터와 계정을 완전히 삭제하려면
        </p>
        <button
          onClick={() => navigate('/delete-account')}
          className="btn btn-outline btn-error w-full"
        >
          계정 영구 삭제
        </button>
      </div>

      {/* 문의 안내 */}
      <p className="text-center text-xs text-base-content/50 mt-4">
        데이터 삭제 관련 문의: help@kims-ai.com
      </p>
    </div>
  );
}
