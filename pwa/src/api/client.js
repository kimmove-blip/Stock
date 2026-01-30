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
  list: () => api.get('/stocks/list'),  // 전체 종목 목록 (자동완성용)
  detail: (code) => api.get(`/stocks/${code}`),
  analysis: (code, scoreVersion = 'v5') => api.get(`/stocks/${code}/analysis?score_version=${scoreVersion}`),
  fundamental: (code) => api.get(`/stocks/${code}/fundamental`),
};

// 포트폴리오 API
export const portfolioAPI = {
  list: () => api.get('/portfolio'),
  add: (data) => api.post('/portfolio', data),
  update: (id, data) => api.put(`/portfolio/${id}`, data),
  delete: (id) => api.delete(`/portfolio/${id}`),
  analysis: () => api.get('/portfolio/analysis'),
  diagnosis: (sortBy = 'holding_value') => api.get(`/portfolio/diagnosis?sort_by=${sortBy}`),
};

// 관심종목 API
export const watchlistAPI = {
  list: (category) => api.get(`/watchlist${category ? `?category=${category}` : ''}`),
  add: (data) => api.post('/watchlist', data),
  delete: (code, category) => api.delete(`/watchlist/${code}?category=${category}`),
};

// TOP 100 API
export const top100API = {
  list: (date, scoreVersion = 'v5') => {
    const params = new URLSearchParams();
    if (date) params.append('date', date);
    params.append('score_version', scoreVersion);
    return api.get(`/top100?${params.toString()}`);
  },
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
  // 캐시된 현재가 (DB)
  cachedPrice: (code) => api.get(`/realtime/cached/price/${code}`),
  cachedPrices: (codes) => api.post('/realtime/cached/prices', codes),
  cacheStatus: () => api.get('/realtime/cached/status'),
  // 하이브리드: 캐시 우선 + 미스시 실시간 조회
  hybridPrices: (codes) => api.get(`/realtime/hybrid/prices?codes=${codes.join(',')}`),
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

// 관리자 API
export const adminAPI = {
  // 회원 목록
  getUsers: () => api.get('/admin/users'),
  // 회원 정보 수정
  updateUser: (userId, data) => api.put(`/admin/users/${userId}`, data),
  // 통계
  getStats: () => api.get('/admin/stats'),
};

// 알림 기록 API
export const alertsAPI = {
  // 알림 기록 조회
  list: (days = 30) => api.get(`/alerts?days=${days}`),
  // 알림 개별 삭제
  delete: (id) => api.delete(`/alerts/${id}`),
  // 알림 기록 전체 삭제
  clear: () => api.delete('/alerts/clear'),
};

// 푸시 알림 API
export const pushAPI = {
  // 설정 조회
  getSettings: () => api.get('/push'),
  // 푸시 구독
  subscribe: (subscription) => api.post('/push/subscribe', subscription),
  // 푸시 구독 해제
  unsubscribe: (endpoint) => api.delete(`/push/unsubscribe${endpoint ? `?endpoint=${encodeURIComponent(endpoint)}` : ''}`),
  // 설정 업데이트
  updateSettings: (data) => api.post('/push/settings', data),
  // 테스트 알림 전송
  test: () => api.post('/push/test'),
  // VAPID 공개키 조회
  getVapidKey: () => api.get('/push/vapid-key'),
};

// 공지사항 API
export const announcementsAPI = {
  // 활성 공지사항 조회
  list: () => api.get('/announcements'),
  // 관리자: 전체 목록
  adminList: () => api.get('/announcements/admin/list'),
  // 관리자: 공지 등록
  adminCreate: (data) => api.post('/announcements/admin', data),
  // 관리자: 공지 수정
  adminUpdate: (id, data) => api.put(`/announcements/admin/${id}`, data),
  // 관리자: 활성/비활성 토글
  adminToggle: (id) => api.put(`/announcements/admin/${id}/toggle`),
  // 관리자: 공지 삭제
  adminDelete: (id) => api.delete(`/announcements/admin/${id}`),
};

// 자동매매 API
export const autoTradeAPI = {
  // 자동매매 현황 조회
  status: () => api.get('/auto-trade/status'),
  // 보유 종목 조회
  holdings: () => api.get('/auto-trade/holdings'),
  // 거래 내역 조회
  trades: (days = 30) => api.get(`/auto-trade/trades?days=${days}`),
  // 매수 제안 조회
  suggestions: (status) => api.get(`/auto-trade/suggestions${status ? `?status=${status}` : ''}`),
  // 성과 분석
  performance: (days = 30) => api.get(`/auto-trade/performance?days=${days}`),
  // 일별 자산 히스토리 (그래프용)
  dailyAsset: (days = 30) => api.get(`/auto-trade/performance/daily-asset?days=${days}`),
  // API 키 설정 조회
  getApiKey: () => api.get('/auto-trade/api-key'),
  // API 키 저장
  saveApiKey: (data) => api.post('/auto-trade/api-key', data),
  // API 키 삭제
  deleteApiKey: () => api.delete('/auto-trade/api-key'),
  // 실제 계좌 현황 조회
  getAccount: () => api.get('/auto-trade/account'),
  // 자동매매 설정 조회
  getSettings: () => api.get('/auto-trade/settings'),
  // 자동매매 설정 저장
  saveSettings: (data) => api.post('/auto-trade/settings', data),
  // 매수 제안 승인 (data: { custom_price?: number, is_market_order?: boolean })
  approveSuggestion: (id, data = {}) => api.post(`/auto-trade/suggestions/${id}/approve`, data),
  // 매수 제안 거부
  rejectSuggestion: (id) => api.post(`/auto-trade/suggestions/${id}/reject`),
  // 매도 제안 조회
  sellSuggestions: (status) => api.get(`/auto-trade/sell-suggestions${status ? `?status=${status}` : ''}`),
  // 매도 제안 승인 (data: { custom_price?: number, is_market_order?: boolean })
  approveSellSuggestion: (id, data = {}) => api.post(`/auto-trade/sell-suggestions/${id}/approve`, data),
  // 매도 제안 거부
  rejectSellSuggestion: (id) => api.post(`/auto-trade/sell-suggestions/${id}/reject`),
  // 보유종목 진단
  getDiagnosis: (sortBy = 'holding_value') => api.get(`/auto-trade/diagnosis?sort_by=${sortBy}`),
  // 수동 주문 실행
  placeOrder: (data) => api.post('/auto-trade/order', data),
  // 미체결 주문 조회
  getPendingOrders: () => api.get('/auto-trade/pending-orders'),
  // 주문 취소
  cancelOrder: (orderId) => api.delete(`/auto-trade/order/${orderId}`),
  // 주문 정정
  modifyOrder: (orderId, data) => api.put(`/auto-trade/pending-orders/${orderId}`, data),
  // 포트폴리오 동기화 (증권 계좌 → 홈 보유종목)
  syncPortfolio: () => api.post('/auto-trade/sync-portfolio'),
  // LLM 설정 조회 (Green Light 모드)
  getLLMSettings: () => api.get('/auto-trade/llm-settings'),
  // LLM 설정 저장
  saveLLMSettings: (data) => api.post('/auto-trade/llm-settings', data),
  // LLM 설정 삭제
  deleteLLMSettings: () => api.delete('/auto-trade/llm-settings'),
  // Green Light 결정 이력 조회
  getGreenlightDecisions: (limit = 20) => api.get(`/auto-trade/greenlight-decisions?limit=${limit}`),
  // 자본 투입/회수 이력 조회
  getCapitalEvents: () => api.get('/auto-trade/capital-events'),
  // 자본 투입/회수 기록
  addCapitalEvent: (data) => api.post('/auto-trade/capital-events', data),
  // 자본 이벤트 삭제
  deleteCapitalEvent: (id) => api.delete(`/auto-trade/capital-events/${id}`),
};

export default api;
