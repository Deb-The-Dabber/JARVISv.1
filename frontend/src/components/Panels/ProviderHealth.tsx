import { useStore } from '../../stores/useAppStore';

export function ProviderHealth() {
  const { providerHealth } = useStore();

  if (providerHealth.length === 0) {
    return (
      <div>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ color: 'var(--fg-dim)' }}>
              <th style={{ textAlign: 'left', padding: '4px 0' }}>Provider</th>
              <th style={{ textAlign: 'right', padding: '4px 0' }}>Health</th>
              <th style={{ textAlign: 'right', padding: '4px 0' }}>S/F</th>
              <th style={{ textAlign: 'right', padding: '4px 0' }}>Lat.</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={4} style={{ textAlign: 'center', color: 'var(--fg-dim)' }}>Loading...</td>
            </tr>
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ color: 'var(--fg-dim)' }}>
            <th style={{ textAlign: 'left', padding: '4px 0' }}>Provider</th>
            <th style={{ textAlign: 'right', padding: '4px 0' }}>Health</th>
            <th style={{ textAlign: 'right', padding: '4px 0' }}>S/F</th>
            <th style={{ textAlign: 'right', padding: '4px 0' }}>Lat.</th>
          </tr>
        </thead>
        <tbody>
          {providerHealth.map((h) => {
            const health = h.health ?? 100;
            const color = health > 70 ? '#4caf50' : health > 30 ? '#ff9800' : '#f44336';
            const circuit = h.circuit_open ? '[RED]' : '[GRN]';
            const latency = h.avg_latency ? String((h.avg_latency * 1000).toFixed(0)) + 'ms' : '-';
            return (
              <tr key={h.name} style={{ color }}>
                <td>{circuit} {h.name}</td>
                <td style={{ textAlign: 'right' }}>{health}%</td>
                <td style={{ textAlign: 'right' }}>{h.successes || 0}/{h.failures || 0}</td>
                <td style={{ textAlign: 'right' }}>{latency}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}