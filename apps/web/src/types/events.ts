export interface RealtimeEvent {
  event_id: string;
  event_type: string;
  tenant_id: string;
  sale_id: string;
  evaluation_run_id?: string | null;
  occurred_at: string;
  version?: number;
}
