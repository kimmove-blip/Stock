import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 요청 인터셉터 - 토큰 추가
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 응답 인터셉터 - 401 에러 처리
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// 인증 API
export const authAPI = {
  login: (username, password) =>
    api.post('/auth/login', new URLSearchParams({ username, password }), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }),
  register: (data) => api.post('/auth/register', data),
  googleLogin: (credential) => api.post('/auth/google', { credential }),
  me: () => api.get('/auth/me'),
  refresh: () => api.post('/auth/refresh'),
  updateSettings: (data) => api.put('/auth/settings', data),
};

// 종목 API
export const stockAPI = {
  search: (q) => api.get(`/stocks/search?q=${encodeURIComponent(q)}`),
  detail: (code) => api.get(`/stocks/${code}`),
  analysis: (code) => api.get(`/stocks/${code}/analysis`),
};

// 포트폴리오 API
export const portfolioAPI = {
  list: () => api.get('/portfolio'),
  add: (data) => api.post('/portfolio', data),
  update: (id, data) => api.put(`/portfolio/${id}`, data),
  delete: (id) => api.delete(`/portfolio/${id}`),
  analysis: () => api.get('/portfolio/analysis'),
};

// 관심종목 API
export const watchlistAPI = {
  list: (category) => api.get(`/watchlist${category ? `?category=${category}` : ''}`),
  add: (data) => api.post('/watchlist', data),
  delete: (code, category) => api.delete(`/watchlist/${code}?category=${category}`),
};

// TOP 100 API
export const top100API = {
  list: (date) => api.get(`/top100${date ? `?date=${date}` : ''}`),
  history: (days = 7) => api.get(`/top100/history?days=${days}`),
  stockHistory: (code) => api.get(`/top100/stock/${code}`),
};

// 실시간 시세 API (한국투자증권)
export const realtimeAPI = {
  // 단일 종목 실시간 시세
  price: (code) => api.get(`/realtime/price/${code}`),
  // 여러 종목 실시간 시세 일괄 조회
  prices: (codes) => api.post('/realtime/prices', codes),
  // TOP100 종목 실시간 시세
  top100Prices: () => api.get('/realtime/top100-prices'),
};

// 가치주 API
export const valueStocksAPI = {
  // 가치주 목록 (대형우량주 포함)
  list: (limit = 30) => api.get(`/value-stocks?limit=${limit}`),
};

// 문의 API
export const contactAPI = {
  // 문의 전송
  submit: (data) => api.post('/contact', data),
  // 관리자: 문의 목록
  adminList: (status) => api.get(`/contact/admin/list${status ? `?status=${status}` : ''}`),
  // 관리자: 문의 상세
  adminDetail: (id) => api.get(`/contact/admin/${id}`),
  // 관리자: 문의 업데이트
  adminUpdate: (id, data) => api.put(`/contact/admin/${id}`, data),
};

// 테마 API
export const themeAPI = {
  // 모든 테마 목록
  list: () => api.get('/themes'),
  // 인기 테마
  popular: (limit = 5) => api.get(`/themes/popular?limit=${limit}`),
  // 테마 검색 (테마명으로 관련 종목 조회)
  search: (q) => api.get(`/themes/search?q=${encodeURIComponent(q)}`),
  // 테마 상세
  detail: (id) => api.get(`/themes/${id}`),
};

// 인기종목 API (실제 거래량/등락률 기준)
export const popularAPI = {
  // 거래량 상위
  volume: (limit = 20) => api.get(`/popular/volume?limit=${limit}`),
  // 상승률 상위
  gainers: (limit = 20) => api.get(`/popular/gainers?limit=${limit}`),
  // 하락률 상위
  losers: (limit = 20) => api.get(`/popular/losers?limit=${limit}`),
};

// 뉴스 API (네이버 뉴스)
export const newsAPI = {
  // 뉴스 검색
  search: (query = '주식 증시', display = 20) =>
    api.get(`/news?query=${encodeURIComponent(query)}&display=${display}`),
  // 카테고리별 뉴스
  byCategory: (category, display = 10) =>
    api.get(`/news/categories?category=${encodeURIComponent(category)}&display=${display}`),
};

// 시장 지수 API
export const marketAPI = {
  // 코스피/코스닥 지수
  domestic: () => api.get('/market'),
  // 해외 지수 및 환율
  global: () => api.get('/market/global'),
};

// 텔레그램 알림 API
export const telegramAPI = {
  // 설정 조회
  getSettings: () => api.get('/telegram'),
  // 설정 업데이트
  updateSettings: (data) => api.post('/telegram', data),
  // Chat ID 검증 및 저장
  verify: (chatId) => api.post('/telegram/verify', { chat_id: chatId }),
  // 테스트 메시지 전송
  test: (chatId) => api.post('/telegram/test', { chat_id: chatId }),
};

export default api;
