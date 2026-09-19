import React, { useState, useRef, useCallback, useEffect } from 'react';

interface StreamChunk {
  speaker: string;
  text: string;
  timestamp_ms: number;
}

interface LiveCheckStatus {
  recording_disclosure: 'PASS' | 'PENDING' | 'FAIL';
  explicit_informed_consent: 'PASS' | 'PENDING' | 'FAIL';
  pci_mute_protocol: 'PASS' | 'PENDING' | 'FAIL';
}

const DEMO_SCRIPT: StreamChunk[] = [
  { speaker: 'AGENT',    text: 'Thank you for calling Energy Australia. My name is Alex.', timestamp_ms: 1200 },
  { speaker: 'AGENT',    text: 'Please be advised that this call is recorded for quality assurance and compliance purposes.', timestamp_ms: 3800 },
  { speaker: 'CUSTOMER', text: 'Hi Alex, I\'d like to compare my current plan with your offers.', timestamp_ms: 8000 },
  { speaker: 'AGENT',    text: 'Of course! Can I confirm that you\'re the account holder or authorised to make changes on the account?', timestamp_ms: 11500 },
  { speaker: 'CUSTOMER', text: 'Yes, I\'m the account holder.', timestamp_ms: 15000 },
  { speaker: 'AGENT',    text: 'Great. Our single rate is 28.6 cents per kilowatt hour with a daily supply charge of 105 cents per day.', timestamp_ms: 18500 },
  { speaker: 'AGENT',    text: 'You also have a 10 business-day cooling off period where you can cancel without penalty or exit fees.', timestamp_ms: 24000 },
  { speaker: 'AGENT',    text: 'I\'ll now pause the recording briefly while you provide payment details. [MUTE ACTIVATED]', timestamp_ms: 29000 },
  { speaker: 'CUSTOMER', text: '[Card details provided offline]', timestamp_ms: 35000 },
  { speaker: 'AGENT',    text: 'Thank you. Recording resumed. Do you give your explicit informed consent to switch to this market offer today?', timestamp_ms: 39000 },
  { speaker: 'CUSTOMER', text: 'Yes, I give my explicit informed consent to proceed.', timestamp_ms: 43000 },
  { speaker: 'AGENT',    text: 'Excellent! Your transfer is confirmed. Welcome to Energy Australia!', timestamp_ms: 47000 },
];

function evaluate(chunks: StreamChunk[]): LiveCheckStatus {
  const text = chunks.map(c => c.text).join(' ').toLowerCase();
  return {
    recording_disclosure:      (text.includes('recorded') || text.includes('quality')) ? 'PASS' : 'PENDING',
    pci_mute_protocol:         (text.includes('mute') || text.includes('pause')) ? 'PASS' : 'PENDING',
    explicit_informed_consent: (text.includes('explicit') || text.includes('consent')) ? 'PASS' : 'PENDING',
  };
}

export const LiveStreamMonitor: React.FC<{ callId?: string }> = ({ callId = 'demo-call-live-1' }) => {
  const [phase, setPhase] = useState<'idle' | 'running' | 'done'>('idle');
  const [chunks, setChunks] = useState<StreamChunk[]>([]);
  const [checks, setChecks] = useState<LiveCheckStatus>({
    recording_disclosure: 'PENDING',
    pci_mute_protocol: 'PENDING',
    explicit_informed_consent: 'PENDING',
  });
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const chunksRef = useRef<StreamChunk[]>([]);
  const transcriptRef = useRef<HTMLDivElement>(null);

  // Auto-scroll transcript
  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [chunks]);

  const clearTimers = () => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
  };

  const start = useCallback(() => {
    clearTimers();
    chunksRef.current = [];
    setChunks([]);
    setChecks({ recording_disclosure: 'PENDING', pci_mute_protocol: 'PENDING', explicit_informed_consent: 'PENDING' });
    setPhase('running');

    DEMO_SCRIPT.forEach((item, i) => {
      const t = setTimeout(() => {
        chunksRef.current = [...chunksRef.current, item];
        const updated = [...chunksRef.current];
        setChunks(updated);
        setChecks(evaluate(updated));
      }, (i + 1) * 1800);
      timersRef.current.push(t);
    });

    const endT = setTimeout(() => {
      setPhase('done');
    }, (DEMO_SCRIPT.length + 1) * 1800);
    timersRef.current.push(endT);
  }, []);

  const stop = () => {
    clearTimers();
    setPhase('idle');
  };

  const reset = () => {
    clearTimers();
    chunksRef.current = [];
    setChunks([]);
    setChecks({ recording_disclosure: 'PENDING', pci_mute_protocol: 'PENDING', explicit_informed_consent: 'PENDING' });
    setPhase('idle');
  };

  const allPassed = checks.recording_disclosure === 'PASS' &&
                    checks.pci_mute_protocol === 'PASS' &&
                    checks.explicit_informed_consent === 'PASS';

  return (
    <div style={{ fontFamily: 'Inter, system-ui, sans-serif', color: '#F9FAFB' }}>
      {/* Header */}
      <div style={{
        background: 'linear-gradient(135deg, #0F172A 0%, #1E293B 100%)',
        borderRadius: '16px',
        padding: '28px 32px',
        marginBottom: '20px',
        border: '1px solid #334155',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        boxShadow: '0 20px 40px rgba(0,0,0,0.4)',
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '6px' }}>
            <div style={{
              width: '40px', height: '40px', borderRadius: '10px',
              background: 'linear-gradient(135deg, #6366F1, #8B5CF6)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '20px', boxShadow: '0 0 20px rgba(99,102,241,0.4)',
            }}>🎙️</div>
            <h2 style={{ margin: 0, fontSize: '1.35rem', fontWeight: 700, letterSpacing: '-0.3px' }}>
              Live Audio Stream Monitor
            </h2>
            <span style={{
              padding: '4px 12px', borderRadius: '20px', fontSize: '0.72rem', fontWeight: 700,
              background: phase === 'running' ? 'rgba(16,185,129,0.15)' : phase === 'done' ? 'rgba(99,102,241,0.15)' : 'rgba(100,116,139,0.2)',
              color: phase === 'running' ? '#34D399' : phase === 'done' ? '#818CF8' : '#94A3B8',
              border: `1px solid ${phase === 'running' ? '#34D39440' : phase === 'done' ? '#818CF840' : '#475569'}`,
            }}>
              {phase === 'running' ? '● STREAMING LIVE' : phase === 'done' ? '✓ AUDIT COMPLETE' : 'READY'}
            </span>
          </div>
          <p style={{ margin: 0, color: '#94A3B8', fontSize: '0.875rem' }}>
            Real-time telephony transcript ingestion with incremental compliance evaluation
          </p>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          {phase === 'idle' && (
            <button id="btn-start-stream" onClick={start} style={{
              background: 'linear-gradient(135deg, #4F46E5, #7C3AED)',
              color: '#FFF', border: 'none', padding: '11px 24px', borderRadius: '10px',
              fontWeight: 600, cursor: 'pointer', fontSize: '0.9rem',
              boxShadow: '0 4px 20px rgba(79,70,229,0.4)', transition: 'all 0.2s',
            }}>
              ▶ Start Audit Simulation
            </button>
          )}
          {phase === 'running' && (
            <button onClick={stop} style={{
              background: '#DC2626', color: '#FFF', border: 'none',
              padding: '11px 20px', borderRadius: '10px', fontWeight: 600, cursor: 'pointer',
            }}>■ Stop</button>
          )}
          {phase === 'done' && (
            <button onClick={reset} style={{
              background: '#1E293B', color: '#CBD5E1', border: '1px solid #334155',
              padding: '11px 20px', borderRadius: '10px', fontWeight: 600, cursor: 'pointer',
            }}>↺ Run Again</button>
          )}
        </div>
      </div>

      {/* Compliance Gate Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '14px', marginBottom: '20px' }}>
        <GateCard label="Call Recording Disclosure" code="TCP Code 2024 cl 4.2" status={checks.recording_disclosure} passText="Disclosed ✓" pendingText="Awaiting..." />
        <GateCard label="PCI-DSS Card Mute Protocol" code="PCI-DSS v4.0 Req 4.2" status={checks.pci_mute_protocol} passText="Muted ✓" pendingText="Awaiting..." />
        <GateCard label="Explicit Informed Consent" code="NERL s 39 / TCP Code cl 4.4" status={checks.explicit_informed_consent} passText="Obtained ✓" pendingText="Awaiting..." />
      </div>

      {/* Live Transcript */}
      <div style={{
        background: '#0F172A', borderRadius: '12px', border: '1px solid #1E293B', overflow: 'hidden',
      }}>
        <div style={{
          padding: '14px 20px', borderBottom: '1px solid #1E293B',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Live Transcript Feed
          </span>
          {chunks.length > 0 && (
            <span style={{ fontSize: '0.75rem', color: '#475569' }}>
              {chunks.length} / {DEMO_SCRIPT.length} utterances
            </span>
          )}
        </div>

        <div ref={transcriptRef} style={{ padding: '16px', maxHeight: '360px', overflowY: 'auto' }}>
          {chunks.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '48px 16px', color: '#475569' }}>
              <div style={{ fontSize: '2.5rem', marginBottom: '12px' }}>🎙️</div>
              <div style={{ fontWeight: 600, color: '#64748B', marginBottom: '4px' }}>No audio stream active</div>
              <div style={{ fontSize: '0.8rem' }}>Press <strong style={{ color: '#818CF8' }}>"Start Audit Simulation"</strong> to begin</div>
            </div>
          ) : (
            chunks.map((chunk, idx) => (
              <UtteranceRow key={idx} chunk={chunk} />
            ))
          )}

          {phase === 'running' && chunks.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 14px', color: '#6366F1', fontSize: '0.8rem' }}>
              <span style={{ animation: 'pulse 1.2s infinite' }}>⬤</span> Listening for next utterance...
            </div>
          )}
        </div>

        {/* Final Verdict */}
        {phase === 'done' && (
          <div style={{
            margin: '0 16px 16px 16px', padding: '16px 20px', borderRadius: '10px',
            background: allPassed ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
            border: `1px solid ${allPassed ? '#10B98130' : '#EF444430'}`,
            display: 'flex', alignItems: 'center', gap: '14px',
          }}>
            <div style={{ fontSize: '2rem' }}>{allPassed ? '✅' : '⛔'}</div>
            <div>
              <div style={{ fontWeight: 700, fontSize: '1rem', color: allPassed ? '#34D399' : '#F87171' }}>
                {allPassed ? 'All compliance gates passed — Sale queued for auto-submission' : 'Critical check failed — Sale held for human review'}
              </div>
              <div style={{ fontSize: '0.8rem', color: '#64748B', marginTop: '2px' }}>
                Call ID: {callId} · Evaluated {DEMO_SCRIPT.length} utterances · Engine: Deterministic (no LLM)
              </div>
            </div>
          </div>
        )}
      </div>

      <style>{`
        @keyframes slideIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
      `}</style>
    </div>
  );
};

const GateCard: React.FC<{
  label: string; code: string;
  status: 'PASS' | 'PENDING' | 'FAIL';
  passText: string; pendingText: string;
}> = ({ label, code, status, passText, pendingText }) => {
  const isPass = status === 'PASS';
  const isFail = status === 'FAIL';
  const color = isPass ? '#10B981' : isFail ? '#EF4444' : '#F59E0B';
  const bg = isPass ? 'rgba(16,185,129,0.07)' : isFail ? 'rgba(239,68,68,0.07)' : 'rgba(245,158,11,0.05)';
  const border = isPass ? '#10B98130' : isFail ? '#EF444430' : '#F59E0B20';

  return (
    <div style={{
      background: bg, borderRadius: '10px', padding: '16px',
      border: `1px solid ${border}`, transition: 'all 0.4s ease',
    }}>
      <div style={{ fontSize: '0.68rem', color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '6px' }}>
        {label}
      </div>
      <div style={{ fontSize: '1.05rem', fontWeight: 700, color, marginBottom: '6px', transition: 'color 0.4s' }}>
        {isPass ? passText : isFail ? '✗ FAILED' : pendingText}
      </div>
      <div style={{ fontSize: '0.68rem', color: '#475569' }}>{code}</div>
    </div>
  );
};

const UtteranceRow: React.FC<{ chunk: StreamChunk }> = ({ chunk }) => (
  <div style={{
    display: 'flex', gap: '12px', marginBottom: '10px',
    animation: 'slideIn 0.3s ease-out',
    flexDirection: chunk.speaker === 'AGENT' ? 'row' : 'row-reverse',
  }}>
    <div style={{
      width: '32px', height: '32px', borderRadius: '50%', flexShrink: 0,
      background: chunk.speaker === 'AGENT'
        ? 'linear-gradient(135deg, #3B82F6, #6366F1)'
        : 'linear-gradient(135deg, #10B981, #059669)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: '14px', fontWeight: 700, color: '#FFF',
    }}>
      {chunk.speaker === 'AGENT' ? 'A' : 'C'}
    </div>
    <div style={{
      maxWidth: '75%',
      background: chunk.speaker === 'AGENT' ? '#1E293B' : '#0F2D25',
      borderRadius: chunk.speaker === 'AGENT' ? '4px 12px 12px 12px' : '12px 4px 12px 12px',
      padding: '10px 14px',
      border: `1px solid ${chunk.speaker === 'AGENT' ? '#334155' : '#1A4035'}`,
    }}>
      <div style={{ fontSize: '0.7rem', fontWeight: 600, color: chunk.speaker === 'AGENT' ? '#60A5FA' : '#34D399', marginBottom: '4px', textTransform: 'uppercase' }}>
        {chunk.speaker} · {(chunk.timestamp_ms / 1000).toFixed(1)}s
      </div>
      <div style={{ fontSize: '0.875rem', color: chunk.text.startsWith('[') ? '#64748B' : '#E2E8F0', lineHeight: 1.5, fontStyle: chunk.text.startsWith('[') ? 'italic' : 'normal' }}>
        {chunk.text}
      </div>
    </div>
  </div>
);
