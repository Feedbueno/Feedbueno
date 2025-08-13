// pages/index.js
export default function Home() {
  if (typeof window !== 'undefined') {
    window.location.href = '/index.html';
  }
  return null;
}