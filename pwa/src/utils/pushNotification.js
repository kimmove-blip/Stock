/**
 * 웹 푸시 알림 유틸리티
 */

const VAPID_PUBLIC_KEY = import.meta.env.VITE_VAPID_PUBLIC_KEY;

/**
 * URL-safe Base64를 Uint8Array로 변환
 */
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding)
    .replace(/-/g, '+')
    .replace(/_/g, '/');

  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

/**
 * 푸시 알림 지원 여부 확인
 */
export function isPushSupported() {
  return (
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

/**
 * 알림 권한 상태 확인
 */
export function getNotificationPermission() {
  if (!('Notification' in window)) {
    return 'unsupported';
  }
  return Notification.permission;
}

/**
 * 알림 권한 요청
 */
export async function requestNotificationPermission() {
  if (!('Notification' in window)) {
    return 'unsupported';
  }

  const permission = await Notification.requestPermission();
  return permission;
}

/**
 * Service Worker 등록 확인
 */
export async function getServiceWorkerRegistration() {
  if (!('serviceWorker' in navigator)) {
    return null;
  }

  const registration = await navigator.serviceWorker.ready;
  return registration;
}

/**
 * 현재 푸시 구독 가져오기
 */
export async function getCurrentSubscription() {
  const registration = await getServiceWorkerRegistration();
  if (!registration) {
    return null;
  }

  const subscription = await registration.pushManager.getSubscription();
  return subscription;
}

/**
 * 푸시 알림 구독
 * @returns {Promise<PushSubscription|null>}
 */
export async function subscribeToPush() {
  try {
    // 권한 확인
    const permission = await requestNotificationPermission();
    if (permission !== 'granted') {
      console.log('알림 권한이 거부되었습니다');
      return null;
    }

    // Service Worker 등록 확인
    const registration = await getServiceWorkerRegistration();
    if (!registration) {
      console.log('Service Worker가 등록되지 않았습니다');
      return null;
    }

    // 기존 구독 확인
    let subscription = await registration.pushManager.getSubscription();

    if (!subscription) {
      // 새 구독 생성
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
      });
    }

    return subscription;
  } catch (error) {
    console.error('푸시 구독 실패:', error);
    return null;
  }
}

/**
 * 푸시 알림 구독 해제
 */
export async function unsubscribeFromPush() {
  try {
    const subscription = await getCurrentSubscription();
    if (subscription) {
      await subscription.unsubscribe();
      return true;
    }
    return false;
  } catch (error) {
    console.error('푸시 구독 해제 실패:', error);
    return false;
  }
}

/**
 * 구독 정보를 서버 API 형식으로 변환
 */
export function subscriptionToJSON(subscription) {
  const json = subscription.toJSON();
  return {
    endpoint: json.endpoint,
    keys: {
      p256dh: json.keys.p256dh,
      auth: json.keys.auth,
    },
  };
}
