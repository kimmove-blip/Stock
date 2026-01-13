import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { UserPlus } from 'lucide-react';

export default function Register() {
  const [formData, setFormData] = useState({
    username: '',
    password: '',
    confirmPassword: '',
    email: '',
    name: '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (formData.password !== formData.confirmPassword) {
      setError('비밀번호가 일치하지 않습니다');
      return;
    }

    if (formData.password.length < 6) {
      setError('비밀번호는 6자 이상이어야 합니다');
      return;
    }

    setLoading(true);

    try {
      await register({
        username: formData.username,
        password: formData.password,
        email: formData.email || undefined,
        name: formData.name || undefined,
      });
      navigate('/');
    } catch (err) {
      setError(err.response?.data?.detail || '회원가입에 실패했습니다');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-base-200 p-4">
      <div className="card w-full max-w-sm bg-base-100 shadow-xl">
        <div className="card-body">
          <div className="text-center mb-4">
            <h1 className="text-2xl font-bold text-primary">AI 주식분석</h1>
            <p className="text-sm text-base-content/60 mt-1">회원가입</p>
          </div>

          <form onSubmit={handleSubmit}>
            {error && (
              <div className="alert alert-error text-sm mb-4">
                <span>{error}</span>
              </div>
            )}

            <div className="form-control">
              <label className="label">
                <span className="label-text">아이디 *</span>
              </label>
              <input
                type="text"
                name="username"
                value={formData.username}
                onChange={handleChange}
                className="input input-bordered"
                placeholder="아이디 입력"
                required
                minLength={3}
              />
            </div>

            <div className="form-control mt-3">
              <label className="label">
                <span className="label-text">비밀번호 *</span>
              </label>
              <input
                type="password"
                name="password"
                value={formData.password}
                onChange={handleChange}
                className="input input-bordered"
                placeholder="6자 이상"
                required
                minLength={6}
              />
            </div>

            <div className="form-control mt-3">
              <label className="label">
                <span className="label-text">비밀번호 확인 *</span>
              </label>
              <input
                type="password"
                name="confirmPassword"
                value={formData.confirmPassword}
                onChange={handleChange}
                className="input input-bordered"
                placeholder="비밀번호 재입력"
                required
              />
            </div>

            <div className="form-control mt-3">
              <label className="label">
                <span className="label-text">이메일</span>
              </label>
              <input
                type="email"
                name="email"
                value={formData.email}
                onChange={handleChange}
                className="input input-bordered"
                placeholder="선택사항"
              />
            </div>

            <div className="form-control mt-3">
              <label className="label">
                <span className="label-text">이름</span>
              </label>
              <input
                type="text"
                name="name"
                value={formData.name}
                onChange={handleChange}
                className="input input-bordered"
                placeholder="선택사항"
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary w-full mt-6"
              disabled={loading}
            >
              {loading ? (
                <span className="loading loading-spinner"></span>
              ) : (
                <>
                  <UserPlus size={18} />
                  가입하기
                </>
              )}
            </button>
          </form>

          <p className="text-center text-sm mt-4">
            이미 계정이 있으신가요?{' '}
            <Link to="/login" className="link link-primary">
              로그인
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
