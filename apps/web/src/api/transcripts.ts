import { apiClient } from "./client";
import { PaginatedSegments } from "../types/transcript";

export async function fetchTranscriptSegments(
  transcriptId: string,
  limit: number = 200,
  includeWords: boolean = false
): Promise<PaginatedSegments> {
  return apiClient<PaginatedSegments>(
    `/api/v1/transcripts/${transcriptId}/segments?limit=${limit}&include_words=${includeWords}`
  );
}
