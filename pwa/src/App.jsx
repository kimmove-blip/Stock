import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { StockCacheProvider } from './contexts/StockCacheContext';
import Layout from './components/Layout';
import Login from './pages/Login';
import Register from './pages/Register';
import Home from './pages/Home';
import Search from './pages/Search';
import Portfolio from './pages/Portfolio';
import Watchlist from './pages/Watchlist';
import StockDetail from './pages/StockDetail';
import About from './pages/About';
import Contact from './pages/Contact';
import Settings from './pages/Settings';
import RealtimePicks from './pages/RealtimePicks';
import ValueStocks from './pages/ValueStocks';
import MarketNews from './pages/MarketNews';
import MarketStatus from './pages/MarketStatus';
import GlobalMarkets from './pages/GlobalMarkets';
import PopularStocks from './pages/PopularStocks';
import Admin from './pages/Admin';
import TelegramSettings from './pages/TelegramSettings';
import PushSettings from './pages/PushSettings';
import AlertHistory from './pages/AlertHistory';
import Privacy from './pages/Privacy';
import DeleteAccount from './pages/DeleteAccount';
import DeleteData from './pages/DeleteData';
import AutoTrade from './pages/AutoTrade';
import AutoTradeApiKey from './pages/AutoTradeApiKey';
import AutoTradeAccount from './pages/AutoTradeAccount';
import AutoTradeSettings from './pages/AutoTradeSettings';
import AutoTradeSuggestions from './pages/AutoTradeSuggestions';
import AutoTradeHistory from './pages/AutoTradeHistory';
import AutoTradePerformance from './pages/AutoTradePerformance';
import AutoTradeDiagnosis from './pages/AutoTradeDiagnosis';
import AutoTradeManual from './pages/AutoTradeManual';
import AutoTradePendingOrders from './pages/AutoTradePendingOrders';
import Loading from './components/Loading';
import Disclaimer from './components/Disclaimer';
import PushPermissionPrompt from './components/PushPermissionPrompt';
import AnnouncementPopup from './components/AnnouncementPopup';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();

  if (loading) {
    return <Loading text="인증 확인 중..." />;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

function PublicRoute({ children }) {
  const { user, loading } = useAuth();

  if (loading) {
    return <Loading text="인증 확인 중..." />;
  }

  if (user) {
    return <Navigate to="/" replace />;
  }

  return children;
}

function AppRoutes() {
  return (
    <Routes>
      {/* 공개 라우트 */}
      <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
      <Route path="/register" element={<PublicRoute><Register /></PublicRoute>} />
      <Route path="/privacy" element={<Privacy />} />

      {/* 보호된 라우트 */}
      <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route path="/" element={<Home />} />
        <Route path="/search" element={<Search />} />
        <Route path="/portfolio" element={<Portfolio />} />
        <Route path="/popular" element={<PopularStocks />} />
        <Route path="/watchlist" element={<Watchlist />} />
        <Route path="/stock/:code" element={<StockDetail />} />
        <Route path="/realtime" element={<RealtimePicks />} />
        <Route path="/value-stocks" element={<ValueStocks />} />
        <Route path="/news" element={<MarketNews />} />
        <Route path="/market" element={<MarketStatus />} />
        <Route path="/global" element={<GlobalMarkets />} />
        <Route path="/about" element={<About />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/telegram" element={<TelegramSettings />} />
        <Route path="/push" element={<PushSettings />} />
        <Route path="/alerts" element={<AlertHistory />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/auto-trade" element={<AutoTrade />} />
        <Route path="/auto-trade/api-key" element={<AutoTradeApiKey />} />
        <Route path="/auto-trade/account" element={<AutoTradeAccount />} />
        <Route path="/auto-trade/settings" element={<AutoTradeSettings />} />
        <Route path="/auto-trade/suggestions" element={<AutoTradeSuggestions />} />
        <Route path="/auto-trade/history" element={<AutoTradeHistory />} />
        <Route path="/auto-trade/performance" element={<AutoTradePerformance />} />
        <Route path="/auto-trade/diagnosis" element={<AutoTradeDiagnosis />} />
        <Route path="/auto-trade/manual" element={<AutoTradeManual />} />
        <Route path="/auto-trade/pending-orders" element={<AutoTradePendingOrders />} />
        <Route path="/delete-account" element={<DeleteAccount />} />
        <Route path="/delete-data" element={<DeleteData />} />
      </Route>

      {/* 404 리다이렉트 */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <StockCacheProvider>
            <Disclaimer />
            <PushPermissionPrompt />
            <AnnouncementPopup />
            <AppRoutes />
          </StockCacheProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
