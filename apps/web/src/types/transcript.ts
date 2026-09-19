export interface WordTiming {
  word: string;
  start_ms: number;
  end_ms: number;
  confidence?: number | null;
}

export interface TranscriptSegment {
  id: string;
  segment_order: number;
  speaker_label: string;
  business_role: "AGENT" | "CUSTOMER" | "UNKNOWN";
  role_confidence: number;
  start_ms: number;
  end_ms: number;
  text: string;
  words?: WordTiming[] | null;
}

export interface PaginatedSegments {
  items: TranscriptSegment[];
  total_count: number;
  offset: number;
  limit: number;
  has_more: boolean;
}
