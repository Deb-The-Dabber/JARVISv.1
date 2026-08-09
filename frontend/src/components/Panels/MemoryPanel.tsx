import { useEffect } from 'react';
import { useStore } from '../../stores/useAppStore';

export function MemoryPanel() {
  const { memoryStats, setMemoryStats, activities, addActivity } = useStore();

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch(`${import.meta.env.VITE_API_URL}/memory/stats`);
        const data = await res.json();
        if (data) {
          setMemoryStats(data);
        }
      } catch (e) {}
    };
    fetchStats();
    const interval = setInterval(fetchStats, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      <div className="panel-title">Memory</div>
      <div id="memoryPanelStatus" style={{ fontSize: '0.65rem', color: 'var(--fg-dim)', lineHeight: '2' }}>
        <div>Facts: {memoryStats?.explicit_memories ?? '?'} entries</div>
        <div>Vector: {memoryStats?.vector_entries ?? '?'} chunks</div>
        <div>RAG: {memoryStats?.rag_chunks ?? '?'} doc chunks</div>
        <div>Graph: {memoryStats?.graph_entities ?? '?'} entities</div>
        <div>Procedures: {memoryStats?.procedures ?? '?'} routines</div>
        <div>Associations: {memoryStats?.associations ?? '?'} pairs</div>
      </div>
    </div>
  );
}
