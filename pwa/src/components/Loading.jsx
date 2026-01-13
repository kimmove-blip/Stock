export default function Loading({ text = '로딩 중...' }) {
  return (
    <div className="flex flex-col items-center justify-center h-64">
      <span className="loading loading-spinner loading-lg text-primary"></span>
      <p className="mt-4 text-base-content/60">{text}</p>
    </div>
  );
}
