/**
 * API 설정
 * 로컬 개발: localhost:8000
 * Vercel 배포: 환경변수 VITE_API_URL 사용
 */

export const getApiUrl = (): string => {
  return import.meta.env.VITE_API_URL || "http://localhost:8000";
};

export const API_URL = getApiUrl();
