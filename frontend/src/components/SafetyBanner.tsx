import { useStore } from '../stores/useAppStore';

export function SafetyBanner() {
  const { safetyBanner, showSafetyBanner, hideSafetyBanner } = useStore();

  if (!safetyBanner) return null;

  return (
    <div className={`safety-banner show ${safetyBanner.type}`}>
      {safetyBanner.message}
    </div>
  );
}