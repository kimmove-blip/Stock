import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { contactAPI, adminAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import {
  MessageSquare,
  Clock,
  CheckCircle,
  XCircle,
  ChevronRight,
  ArrowLeft,
  Send,
  AlertCircle,
  ShieldX,
  Users,
  Mail,
  MessageCircle,
  Shield,
  ShieldOff,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Briefcase,
  Star,
  Calendar,
} from 'lucide-react';

// 상태 배지 컴포넌트
function StatusBadge({ status }) {
  const styles = {
    pending: 'bg-yellow-100 text-yellow-800',
    replied: 'bg-blue-100 text-blue-800',
    resolved: 'bg-green-100 text-green-800',
  };
  const labels = {
    pending: '대기중',
    replied: '답변완료',
    resolved: '해결됨',
  };
  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium ${styles[status] || 'bg-gray-100 text-gray-800'}`}>
      {labels[status] || status}
    </span>
  );
}

// 문의 상세 모달
function ContactDetail({ contact, onClose, onUpdate }) {
  const [status, setStatus] = useState(contact.status);
  const [reply, setReply] = useState(contact.admin_reply || '');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      await onUpdate(contact.id, { status, admin_reply: reply });
      onClose();
    } catch (error) {
      alert('업데이트 실패');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        {/* 헤더 */}
        <div className="sticky top-0 bg-white border-b p-4 flex items-center gap-3">
          <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded-lg">
            <ArrowLeft size={20} />
          </button>
          <h2 className="font-bold text-lg">문의 상세</h2>
        </div>

        {/* 내용 */}
        <div className="p-4 space-y-4">
          {/* 문의 정보 */}
          <div className="bg-gray-50 rounded-lg p-4 space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-500">사용자</span>
              <span className="font-medium">{contact.name || contact.username || '비로그인'}</span>
            </div>
            {contact.email && (
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-500">이메일</span>
                <span className="font-medium">{contact.email}</span>
              </div>
            )}
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-500">접수일시</span>
              <span className="text-sm">{new Date(contact.created_at).toLocaleString('ko-KR')}</span>
            </div>
          </div>

          {/* 문의 내용 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">문의 내용</label>
            <div className="bg-gray-50 rounded-lg p-4 text-gray-700 whitespace-pre-wrap">
              {contact.message}
            </div>
          </div>

          {/* 상태 선택 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">상태</label>
            <div className="flex gap-2">
              {['pending', 'replied', 'resolved'].map((s) => (
                <button
                  key={s}
                  onClick={() => setStatus(s)}
                  className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-all ${
                    status === s
                      ? 'bg-purple-600 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {s === 'pending' && '대기중'}
                  {s === 'replied' && '답변완료'}
                  {s === 'resolved' && '해결됨'}
                </button>
              ))}
            </div>
          </div>

          {/* 관리자 답변 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">관리자 메모</label>
            <textarea
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              placeholder="내부 메모를 입력하세요..."
              rows={4}
              className="w-full px-4 py-3 border border-gray-200 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none"
            />
          </div>

          {/* 저장 버튼 */}
          <button
            onClick={handleSubmit}
            disabled={isSubmitting}
            className="w-full py-3 bg-purple-600 text-white rounded-lg font-medium hover:bg-purple-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {isSubmitting ? (
              <span>저장 중...</span>
            ) : (
              <>
                <Send size={18} />
                <span>저장하기</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// 문의 관리 탭
function ContactsTab() {
  const [filter, setFilter] = useState('all');
  const [selectedContact, setSelectedContact] = useState(null);
  const queryClient = useQueryClient();

  // 문의 목록 조회
  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-contacts', filter],
    queryFn: () => contactAPI.adminList(filter === 'all' ? null : filter).then((res) => res.data),
    refetchInterval: 30000,
  });

  // 문의 업데이트
  const updateMutation = useMutation({
    mutationFn: ({ id, data }) => contactAPI.adminUpdate(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries(['admin-contacts']);
    },
  });

  const handleUpdate = async (id, updateData) => {
    await updateMutation.mutateAsync({ id, data: updateData });
  };

  const filters = [
    { key: 'all', label: '전체', icon: MessageSquare },
    { key: 'pending', label: '대기중', icon: Clock },
    { key: 'replied', label: '답변완료', icon: CheckCircle },
    { key: 'resolved', label: '해결됨', icon: XCircle },
  ];

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <AlertCircle size={48} className="text-red-400 mb-4" />
        <p className="text-gray-500">문의 목록을 불러올 수 없습니다</p>
      </div>
    );
  }

  return (
    <>
      {/* 필터 탭 */}
      <div className="flex gap-2 mb-4 overflow-x-auto pb-2">
        {filters.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setFilter(key)}
            className={`flex items-center gap-2 px-4 py-2 rounded-full whitespace-nowrap transition-all ${
              filter === key
                ? 'bg-purple-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            <Icon size={16} />
            <span className="text-sm font-medium">{label}</span>
            {key === 'pending' && data?.pending_count > 0 && (
              <span className="bg-red-500 text-white text-xs px-1.5 py-0.5 rounded-full">
                {data.pending_count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* 문의 목록 */}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-purple-600 border-t-transparent"></div>
        </div>
      ) : data?.items?.length === 0 ? (
        <div className="text-center py-12">
          <MessageSquare size={48} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500">문의 내역이 없습니다</p>
        </div>
      ) : (
        <div className="space-y-3">
          {data?.items?.map((contact) => (
            <button
              key={contact.id}
              onClick={() => setSelectedContact(contact)}
              className="w-full bg-white rounded-xl p-4 shadow-sm hover:shadow-md transition-shadow text-left"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-gray-800">
                      {contact.name || contact.username || '비로그인'}
                    </span>
                    <StatusBadge status={contact.status} />
                  </div>
                  <p className="text-gray-600 text-sm line-clamp-2 mb-2">
                    {contact.message}
                  </p>
                  <p className="text-xs text-gray-400">
                    {new Date(contact.created_at).toLocaleString('ko-KR')}
                  </p>
                </div>
                <ChevronRight size={20} className="text-gray-400 flex-shrink-0 mt-1" />
              </div>
            </button>
          ))}
        </div>
      )}

      {/* 문의 상세 모달 */}
      {selectedContact && (
        <ContactDetail
          contact={selectedContact}
          onClose={() => setSelectedContact(null)}
          onUpdate={handleUpdate}
        />
      )}
    </>
  );
}

// 회원 관리 탭
function UsersTab({ currentUser }) {
  const queryClient = useQueryClient();
  const [expandedUser, setExpandedUser] = useState(null);

  // 통계 조회
  const { data: stats } = useQuery({
    queryKey: ['adminStats'],
    queryFn: () => adminAPI.getStats().then((res) => res.data),
    staleTime: 1000 * 60 * 5,
  });

  // 회원 목록 조회
  const { data: usersData, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['adminUsers'],
    queryFn: () => adminAPI.getUsers().then((res) => res.data),
    staleTime: 1000 * 60 * 5,
  });

  // 회원 권한 수정
  const updateMutation = useMutation({
    mutationFn: ({ userId, data }) => adminAPI.updateUser(userId, data),
    onSuccess: () => {
      queryClient.invalidateQueries(['adminUsers']);
      queryClient.invalidateQueries(['adminStats']);
    },
    onError: (error) => {
      alert(error.response?.data?.detail || '수정에 실패했습니다');
    },
  });

  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('ko-KR', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const formatDateTime = (dateStr) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('ko-KR', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const users = usersData?.users || [];

  return (
    <>
      {/* 통계 카드 */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <Users size={18} className="text-blue-500" />
            <span className="text-sm text-gray-500">총 회원</span>
          </div>
          <p className="text-2xl font-bold text-gray-800">{stats?.total_users || 0}명</p>
          <p className="text-xs text-green-500">오늘 +{stats?.today_users || 0}</p>
        </div>
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <Mail size={18} className="text-purple-500" />
            <span className="text-sm text-gray-500">이메일 구독</span>
          </div>
          <p className="text-2xl font-bold text-gray-800">{stats?.email_subscribers || 0}명</p>
        </div>
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <MessageCircle size={18} className="text-blue-400" />
            <span className="text-sm text-gray-500">텔레그램</span>
          </div>
          <p className="text-2xl font-bold text-gray-800">{stats?.telegram_subscribers || 0}명</p>
        </div>
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <MessageSquare size={18} className="text-orange-500" />
            <span className="text-sm text-gray-500">대기 문의</span>
          </div>
          <p className="text-2xl font-bold text-gray-800">{stats?.pending_contacts || 0}건</p>
        </div>
      </div>

      {/* 회원 목록 헤더 */}
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-bold text-gray-800">회원 목록 ({users.length}명)</h2>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="btn btn-sm btn-ghost gap-2"
        >
          <RefreshCw size={16} className={isFetching ? 'animate-spin' : ''} />
          새로고침
        </button>
      </div>

      {/* 회원 목록 */}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-purple-600 border-t-transparent"></div>
        </div>
      ) : (
        <div className="space-y-3">
          {users.map((member) => (
            <div
              key={member.id}
              className="bg-white rounded-xl shadow-sm overflow-hidden"
            >
              {/* 기본 정보 */}
              <button
                onClick={() => setExpandedUser(expandedUser === member.id ? null : member.id)}
                className="w-full p-4 flex items-center justify-between hover:bg-gray-50"
              >
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center text-white font-bold ${
                    member.is_admin ? 'bg-gradient-to-br from-purple-600 to-indigo-600' : 'bg-gray-400'
                  }`}>
                    {(member.name || member.username)?.charAt(0)?.toUpperCase() || 'U'}
                  </div>
                  <div className="text-left">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-gray-800">{member.name || member.username}</span>
                      {member.is_admin && (
                        <span className="bg-purple-100 text-purple-600 text-xs px-1.5 py-0.5 rounded">
                          관리자
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-500">{member.email || '-'}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {member.telegram_enabled && (
                    <MessageCircle size={14} className="text-blue-400" />
                  )}
                  {member.email_subscription && (
                    <Mail size={14} className="text-purple-500" />
                  )}
                  {expandedUser === member.id ? (
                    <ChevronUp size={18} className="text-gray-400" />
                  ) : (
                    <ChevronDown size={18} className="text-gray-400" />
                  )}
                </div>
              </button>

              {/* 상세 정보 */}
              {expandedUser === member.id && (
                <div className="px-4 pb-4 border-t border-gray-100 pt-3">
                  <div className="grid grid-cols-2 gap-3 mb-3 text-sm">
                    <div className="flex items-center gap-2">
                      <Calendar size={14} className="text-gray-400" />
                      <span className="text-gray-500">가입:</span>
                      <span className="text-gray-700">{formatDate(member.created_at)}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Clock size={14} className="text-gray-400" />
                      <span className="text-gray-500">최근:</span>
                      <span className="text-gray-700">{formatDateTime(member.last_login)}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Briefcase size={14} className="text-gray-400" />
                      <span className="text-gray-500">보유종목:</span>
                      <span className="text-gray-700">{member.portfolio_count}개</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Star size={14} className="text-gray-400" />
                      <span className="text-gray-500">관심종목:</span>
                      <span className="text-gray-700">{member.watchlist_count}개</span>
                    </div>
                  </div>

                  {/* 관리자 권한 토글 */}
                  {member.id !== currentUser.id && (
                    <div className="flex gap-2">
                      <button
                        onClick={() => updateMutation.mutate({
                          userId: member.id,
                          data: { is_admin: !member.is_admin }
                        })}
                        disabled={updateMutation.isPending}
                        className={`flex-1 btn btn-sm gap-2 ${
                          member.is_admin
                            ? 'btn-outline btn-error'
                            : 'btn-outline btn-primary'
                        }`}
                      >
                        {member.is_admin ? (
                          <>
                            <ShieldOff size={14} />
                            관리자 해제
                          </>
                        ) : (
                          <>
                            <Shield size={14} />
                            관리자 지정
                          </>
                        )}
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {users.length === 0 && !isLoading && (
        <div className="text-center py-10 text-gray-500">
          회원이 없습니다
        </div>
      )}
    </>
  );
}

export default function Admin() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('users');

  // 관리자 권한 체크
  if (!user?.is_admin) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <ShieldX size={64} className="text-red-400 mb-4" />
        <h2 className="text-xl font-bold text-gray-800 mb-2">접근 권한 없음</h2>
        <p className="text-gray-500 mb-6">관리자만 접근할 수 있습니다.</p>
        <button
          onClick={() => navigate('/')}
          className="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
        >
          홈으로 돌아가기
        </button>
      </div>
    );
  }

  const tabs = [
    { key: 'users', label: '회원 관리', icon: Users },
    { key: 'contacts', label: '문의 관리', icon: MessageSquare },
  ];

  return (
    <div className="max-w-2xl mx-auto pb-20">
      {/* 헤더 */}
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-gray-800">관리자</h1>
      </div>

      {/* 탭 선택 */}
      <div className="flex gap-2 mb-4">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`flex items-center gap-2 px-4 py-2 rounded-full transition-all ${
              activeTab === key
                ? 'bg-purple-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            <Icon size={16} />
            <span className="text-sm font-medium">{label}</span>
          </button>
        ))}
      </div>

      {/* 탭 내용 */}
      {activeTab === 'users' && <UsersTab currentUser={user} />}
      {activeTab === 'contacts' && <ContactsTab />}
    </div>
  );
}
