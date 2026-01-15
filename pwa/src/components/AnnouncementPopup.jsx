import { useState, useEffect } from 'react';
import { X, AlertTriangle, Info, AlertCircle } from 'lucide-react';
import { announcementsAPI } from '../api/client';

const DISMISSED_KEY = 'dismissed_announcements';

export default function AnnouncementPopup() {
  const [announcements, setAnnouncements] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    fetchAnnouncements();
  }, []);

  const fetchAnnouncements = async () => {
    try {
      const res = await announcementsAPI.list();
      const dismissed = JSON.parse(localStorage.getItem(DISMISSED_KEY) || '[]');

      // show_once인 공지 중 이미 본 것은 제외
      const filtered = res.data.filter((ann) => {
        if (ann.show_once && dismissed.includes(ann.id)) {
          return false;
        }
        return true;
      });

      setAnnouncements(filtered);
    } catch (error) {
      console.error('공지사항 로드 실패:', error);
    }
  };

  const handleDismiss = () => {
    const current = announcements[currentIndex];

    // show_once인 경우 localStorage에 저장
    if (current.show_once) {
      const dismissed = JSON.parse(localStorage.getItem(DISMISSED_KEY) || '[]');
      if (!dismissed.includes(current.id)) {
        dismissed.push(current.id);
        localStorage.setItem(DISMISSED_KEY, JSON.stringify(dismissed));
      }
    }

    // 다음 공지로 이동 또는 닫기
    if (currentIndex < announcements.length - 1) {
      setCurrentIndex(currentIndex + 1);
    } else {
      setAnnouncements([]);
    }
  };

  if (announcements.length === 0) {
    return null;
  }

  const current = announcements[currentIndex];

  const getIcon = (type) => {
    switch (type) {
      case 'warning':
        return <AlertTriangle className="text-yellow-500" size={24} />;
      case 'error':
        return <AlertCircle className="text-red-500" size={24} />;
      default:
        return <Info className="text-blue-500" size={24} />;
    }
  };

  const getBgColor = (type) => {
    switch (type) {
      case 'warning':
        return 'bg-yellow-50 border-yellow-200';
      case 'error':
        return 'bg-red-50 border-red-200';
      default:
        return 'bg-blue-50 border-blue-200';
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className={`bg-white rounded-2xl shadow-xl max-w-md w-full overflow-hidden`}>
        {/* Header */}
        <div className={`${getBgColor(current.type)} border-b px-4 py-3 flex items-center justify-between`}>
          <div className="flex items-center gap-2">
            {getIcon(current.type)}
            <span className="font-bold text-gray-800">공지사항</span>
            {announcements.length > 1 && (
              <span className="text-xs text-gray-500">
                ({currentIndex + 1}/{announcements.length})
              </span>
            )}
          </div>
          <button
            onClick={handleDismiss}
            className="p-1 hover:bg-gray-200 rounded-full transition"
          >
            <X size={20} className="text-gray-600" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4">
          <h3 className="font-bold text-lg text-gray-800 mb-2">{current.title}</h3>
          <p className="text-gray-600 whitespace-pre-wrap">{current.content}</p>
        </div>

        {/* Footer */}
        <div className="px-4 pb-4 flex justify-end gap-2">
          {current.show_once && (
            <span className="text-xs text-gray-400 self-center mr-auto">
              다시 표시되지 않습니다
            </span>
          )}
          <button
            onClick={handleDismiss}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg font-medium hover:bg-blue-600 transition"
          >
            확인
          </button>
        </div>
      </div>
    </div>
  );
}
