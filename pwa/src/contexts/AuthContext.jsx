import { createContext, useContext, useState, useEffect } from 'react';
import { authAPI } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    const token = localStorage.getItem('token');
    if (!token) {
      setLoading(false);
      return;
    }

    try {
      const { data } = await authAPI.me();
      setUser(data);
    } catch (error) {
      localStorage.removeItem('token');
    } finally {
      setLoading(false);
    }
  };

  const login = async (username, password) => {
    const { data } = await authAPI.login(username, password);
    localStorage.setItem('token', data.access_token);
    const { data: userData } = await authAPI.me();
    setUser(userData);
    return userData;
  };

  const register = async (userData) => {
    await authAPI.register(userData);
    return login(userData.username, userData.password);
  };

  const googleLogin = async (credential) => {
    const { data } = await authAPI.googleLogin(credential);
    localStorage.setItem('token', data.access_token);
    const { data: userData } = await authAPI.me();
    setUser(userData);
    return userData;
  };

  const logout = () => {
    localStorage.removeItem('token');
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, googleLogin, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
