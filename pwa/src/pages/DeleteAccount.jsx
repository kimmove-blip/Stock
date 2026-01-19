import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, AlertTriangle } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

export default function DeleteAccount() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [confirmed, setConfirmed] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleted, setDeleted] = useState(false);

  const handleDelete = async () => {
    if (!confirmed) {
      alert('체크박스를 선택해주세요.');
      return;
    }

    if (!confirm('정말로 계정을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.')) {
      return;
    }

    setDeleting(true);

    try {
      const response = await fetch('/api/auth/delete-account', {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
      });

      if (response.ok) {
        setDeleted(true);
        setTimeout(() => {
          logout();
          navigate('/');
        }, 3000);
      } else {
        const data = await response.json();
        alert(data.detail || '계정 삭제에 실패했습니다.');
      }
    } catch (error) {
      alert('계정 삭제 중 오류가 발생했습니다.');
    } finally {
      setDeleting(false);
    }
  };

  if (deleted) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="text-center">
          <h2 className="text-xl font-bold mb-2">계정이 삭제되었습니다</h2>
          <p className="text-base-content/60">이용해 주셔서 감사합니다.</p>
          <p className="text-sm text-base-content/40 mt-2">잠시 후 홈으로 이동합니다...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="pb-20">
      {/* 헤더 */}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate(-1)} className="btn btn-ghost btn-sm">
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-xl font-bold">계정 삭제</h1>
      </div>

      {/* 경고 */}
      <div className="alert alert-warning mb-6">
        <AlertTriangle size={24} />
        <div>
          <h3 className="font-bold">주의</h3>
          <p className="text-sm">계정을 삭제하면 모든 데이터가 영구적으로 삭제되며 복구할 수 없습니다.</p>
        </div>
      </div>

      {/* 삭제되는 데이터 */}
      <div className="card bg-base-100 shadow mb-6">
        <div className="card-body">
          <h2 className="card-title text-base">삭제되는 데이터</h2>
          <ul className="list-disc list-inside text-sm space-y-1 text-base-content/70">
            <li>계정 정보 (이메일, 이름)</li>
            <li>보유 종목 데이터</li>
            <li>관심 종목 목록</li>
            <li>포트폴리오 기록</li>
            <li>텔레그램 연동 정보</li>
            <li>앱 설정 및 환경설정</li>
          </ul>
        </div>
      </div>

      {/* 삭제 처리 기간 */}
      <div className="card bg-base-100 shadow mb-6">
        <div className="card-body">
          <h2 className="card-title text-base">삭제 처리</h2>
          <p className="text-sm text-base-content/70">
            계정 삭제 요청 시 모든 개인정보는 즉시 삭제됩니다.
            단, 법령에 따라 보관이 필요한 정보는 해당 기간 동안 보관 후 파기됩니다.
          </p>
        </div>
      </div>

      {/* 확인 체크박스 */}
      <div className="form-control mb-6">
        <label className="label cursor-pointer justify-start gap-3">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
            className="checkbox checkbox-error"
          />
          <span className="label-text">
            위 내용을 확인했으며, 계정 삭제에 동의합니다.
          </span>
        </label>
      </div>

      {/* 삭제 버튼 */}
      <button
        onClick={handleDelete}
        disabled={!confirmed || deleting}
        className="btn btn-error w-full"
      >
        {deleting ? (
          <span className="loading loading-spinner"></span>
        ) : (
          '계정 영구 삭제'
        )}
      </button>

      {/* 문의 안내 */}
      <p className="text-center text-xs text-base-content/50 mt-4">
        계정 삭제 관련 문의: help@kims-ai.com
      </p>
    </div>
  );
}
