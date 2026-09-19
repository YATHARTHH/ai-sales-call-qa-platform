import React, { useEffect, useRef, useState } from "react";
import { Play, Pause, RotateCcw, FastForward } from "lucide-react";

interface AudioPlayerProps {
  recordingId?: string | null;
  currentTimeMs: number;
  onTimeUpdate: (ms: number) => void;
  seekTargetMs: number | null;
  onSeekHandled: () => void;
}

export const AudioPlayer: React.FC<AudioPlayerProps> = ({
  recordingId,
  currentTimeMs,
  onTimeUpdate,
  seekTargetMs,
  onSeekHandled,
}) => {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [durationSec, setDurationSec] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1.0);

  const audioUrl = recordingId ? `/api/v1/recordings/${recordingId}/audio` : null;

  // Handle external seek targets (e.g. clicking evidence badge or transcript line)
  useEffect(() => {
    if (seekTargetMs !== null && audioRef.current) {
      audioRef.current.currentTime = seekTargetMs / 1000;
      onSeekHandled();
      if (!isPlaying) {
        audioRef.current.play().catch(() => {});
        setIsPlaying(true);
      }
    }
  }, [seekTargetMs]);

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play().catch(() => {});
      setIsPlaying(true);
    }
  };

  const handleTimeUpdate = () => {
    if (!audioRef.current) return;
    onTimeUpdate(Math.floor(audioRef.current.currentTime * 1000));
  };

  const handleLoadedMetadata = () => {
    if (!audioRef.current) return;
    setDurationSec(audioRef.current.duration || 0);
  };

  const handleProgressChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newSec = parseFloat(e.target.value);
    if (audioRef.current) {
      audioRef.current.currentTime = newSec;
      onTimeUpdate(Math.floor(newSec * 1000));
    }
  };

  const changeSpeed = () => {
    const rates = [0.75, 1.0, 1.25, 1.5, 2.0];
    const nextIdx = (rates.indexOf(playbackRate) + 1) % rates.length;
    const nextRate = rates[nextIdx];
    setPlaybackRate(nextRate);
    if (audioRef.current) {
      audioRef.current.playbackRate = nextRate;
    }
  };

  const formatTime = (ms: number) => {
    const totalSec = Math.floor(ms / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  if (!audioUrl) {
    return (
      <div style={{ padding: "16px", textAlign: "center", color: "var(--text-muted)", fontSize: "14px" }}>
        No audio recording available for this call
      </div>
    );
  }

  return (
    <div
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-lg)",
        padding: "14px 20px",
        display: "flex",
        alignItems: "center",
        gap: "20px",
        boxShadow: "var(--shadow-md)",
      }}
    >
      <audio
        ref={audioRef}
        src={audioUrl}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onEnded={() => setIsPlaying(false)}
      />

      <button
        onClick={togglePlay}
        style={{
          width: "44px",
          height: "44px",
          borderRadius: "50%",
          background: "var(--brand-cyan)",
          color: "#090d16",
          border: "none",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: "var(--shadow-glow-cyan)",
          transition: "var(--transition-fast)",
        }}
      >
        {isPlaying ? <Pause size={20} fill="#090d16" /> : <Play size={20} fill="#090d16" />}
      </button>

      <button
        onClick={() => {
          if (audioRef.current) {
            audioRef.current.currentTime = Math.max(0, audioRef.current.currentTime - 5);
          }
        }}
        title="Rewind 5s"
        style={{
          background: "transparent",
          border: "none",
          color: "var(--text-secondary)",
          cursor: "pointer",
          padding: "4px",
        }}
      >
        <RotateCcw size={18} />
      </button>

      <div style={{ display: "flex", alignItems: "center", gap: "10px", flex: 1 }}>
        <span style={{ fontSize: "13px", fontFamily: "var(--font-mono)", color: "var(--text-secondary)", width: "45px" }}>
          {formatTime(currentTimeMs)}
        </span>
        <input
          type="range"
          min={0}
          max={durationSec || 100}
          step={0.1}
          value={currentTimeMs / 1000}
          onChange={handleProgressChange}
          style={{
            flex: 1,
            accentColor: "var(--brand-cyan)",
            cursor: "pointer",
            height: "5px",
          }}
        />
        <span style={{ fontSize: "13px", fontFamily: "var(--font-mono)", color: "var(--text-muted)", width: "45px" }}>
          {formatTime(durationSec * 1000)}
        </span>
      </div>

      <button
        onClick={changeSpeed}
        style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border-subtle)",
          color: "var(--text-primary)",
          borderRadius: "var(--radius-sm)",
          padding: "4px 10px",
          fontSize: "12px",
          fontWeight: 600,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: "4px",
        }}
      >
        <FastForward size={14} />
        {playbackRate}x
      </button>
    </div>
  );
};
