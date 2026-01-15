import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { stockAPI } from '../api/client';

const StockCacheContext = createContext(null);

const CACHE_KEY = 'stock_list_cache';
const CACHE_TTL = 1000 * 60 * 60; // 1시간

export function StockCacheProvider({ children }) {
  const [stocks, setStocks] = useState([]);
  const [loading, setLoading] = useState(true);

  // 캐시에서 로드 또는 API 호출
  useEffect(() => {
    loadStocks();
  }, []);

  const loadStocks = async () => {
    // localStorage 캐시 확인
    try {
      const cached = localStorage.getItem(CACHE_KEY);
      if (cached) {
        const { data, timestamp } = JSON.parse(cached);
        if (Date.now() - timestamp < CACHE_TTL) {
          setStocks(data);
          setLoading(false);
          return;
        }
      }
    } catch (e) {
      console.error('Cache read error:', e);
    }

    // API에서 로드
    try {
      const res = await stockAPI.list();
      const stockList = res.data?.stocks || [];
      setStocks(stockList);

      // 캐시 저장
      localStorage.setItem(CACHE_KEY, JSON.stringify({
        data: stockList,
        timestamp: Date.now(),
      }));
    } catch (error) {
      console.error('Failed to load stock list:', error);
    } finally {
      setLoading(false);
    }
  };

  // 즉시 검색 (클라이언트 사이드)
  const searchStocks = useCallback((query, limit = 20) => {
    if (!query || query.length === 0) return [];

    const q = query.toLowerCase();
    const results = [];

    for (const stock of stocks) {
      // 종목명 또는 종목코드로 검색
      if (
        stock.name.toLowerCase().includes(q) ||
        stock.code.toLowerCase().includes(q)
      ) {
        results.push(stock);
        if (results.length >= limit) break;
      }
    }

    return results;
  }, [stocks]);

  // prefix 검색 (한글 초성 지원 - 종목명 시작 부분 매칭 우선, 가나다순 정렬)
  const searchStocksPrefix = useCallback((query, limit = 20) => {
    if (!query || query.length === 0) return [];

    const q = query.toLowerCase();
    const prefixResults = [];
    const containsResults = [];

    for (const stock of stocks) {
      const nameLower = stock.name.toLowerCase();
      const codeLower = stock.code.toLowerCase();

      // prefix 매칭 (시작 부분)
      if (nameLower.startsWith(q) || codeLower.startsWith(q)) {
        prefixResults.push(stock);
      }
      // contains 매칭 (포함)
      else if (nameLower.includes(q) || codeLower.includes(q)) {
        containsResults.push(stock);
      }

      if (prefixResults.length + containsResults.length >= limit * 2) break;
    }

    // 가나다순 정렬
    const sortByName = (a, b) => a.name.localeCompare(b.name, 'ko');
    prefixResults.sort(sortByName);
    containsResults.sort(sortByName);

    // prefix 결과 우선, 그 다음 contains 결과
    return [...prefixResults, ...containsResults].slice(0, limit);
  }, [stocks]);

  return (
    <StockCacheContext.Provider value={{
      stocks,
      loading,
      searchStocks,
      searchStocksPrefix,
      refresh: loadStocks,
    }}>
      {children}
    </StockCacheContext.Provider>
  );
}

export function useStockCache() {
  const context = useContext(StockCacheContext);
  if (!context) {
    throw new Error('useStockCache must be used within StockCacheProvider');
  }
  return context;
}
