import { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { contactAPI } from '../api/client';
import { Mail, Send, CheckCircle } from 'lucide-react';

export default function Contact() {
  const { user } = useAuth();
  const [message, setMessage] = useState('');
  const [email, setEmail] = useState('');
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!message.trim() || message.length < 10) {
      setError('문의 내용은 최소 10자 이상 입력해주세요.');
      return;
    }

    setSending(true);
    setError('');

    try {
      await contactAPI.submit({
        message: message.trim(),
        email: email || user?.email || null,
        username: user?.username || null,
      });
      setSent(true);
      setMessage('');
      setEmail('');
    } catch (err) {
      setError('문의 전송에 실패했습니다. 다시 시도해주세요.');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="max-w-md mx-auto">
      {/* 문의 폼 */}
      <div className="bg-white rounded-xl p-4 shadow-sm">
        {sent ? (
          <div className="text-center py-8">
            <div className="w-16 h-16 bg-green-100 rounded-full mx-auto flex items-center justify-center mb-4">
              <CheckCircle size={32} className="text-green-600" />
            </div>
            <h3 className="font-semibold text-gray-800">문의가 전송되었습니다</h3>
            <p className="text-sm text-gray-500 mt-2">
              관리자 이메일로 문의 내용이 전달되었습니다.<br />
              빠른 시일 내에 답변 드리겠습니다.
            </p>
            <button
              onClick={() => setSent(false)}
              className="mt-4 text-purple-600 text-sm font-medium"
            >
              새 문의 작성
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            {/* 이메일 (선택) */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                답변 받을 이메일 (선택)
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder={user?.email || "example@email.com"}
              />
            </div>

            {/* 문의 내용 */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                문의 내용 <span className="text-red-500">*</span>
              </label>
              <textarea
                value={message}
                onChange={(e) => {
                  setMessage(e.target.value);
                  setError('');
                }}
                rows={5}
                className="w-full px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
                placeholder="문의 내용을 입력하세요... (최소 10자)"
                required
              />
              <p className="text-xs text-gray-400 mt-1 text-right">
                {message.length}자
              </p>
            </div>

            {error && (
              <p className="text-red-500 text-sm mb-4">{error}</p>
            )}

            <button
              type="submit"
              disabled={sending}
              className="w-full bg-purple-600 text-white py-3 rounded-xl font-medium hover:bg-purple-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {sending ? (
                <>
                  <span className="loading loading-spinner loading-sm"></span>
                  전송 중...
                </>
              ) : (
                <>
                  <Send size={18} />
                  문의 보내기
                </>
              )}
            </button>
          </form>
        )}
      </div>

      {/* 연락처 정보 */}
      <div className="mt-6 bg-white rounded-xl p-4 shadow-sm">
        <h3 className="font-semibold text-gray-800 mb-3">다른 연락 방법</h3>
        <div className="flex items-center gap-3 text-gray-600">
          <Mail size={20} />
          <span className="text-sm">gimb4753@gmail.com</span>
        </div>
        <p className="text-xs text-gray-400 mt-3">
          문의하신 내용은 관리자 이메일로 전송되며,<br />
          입력하신 이메일로 답변을 드립니다.
        </p>
      </div>
    </div>
  );
}
