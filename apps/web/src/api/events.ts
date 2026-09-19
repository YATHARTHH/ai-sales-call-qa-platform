import { RealtimeEvent } from "../types/events";
import { getTenantId } from "./client";

export function subscribeToEvents(
  onEvent: (event: RealtimeEvent) => void,
  tenantId?: string
): () => void {
  const activeTenant = tenantId || getTenantId();
  const url = `/api/v1/events/stream?tenant_id=${encodeURIComponent(activeTenant)}`;
  const eventSource = new EventSource(url);

  const handleMessage = (evt: MessageEvent) => {
    try {
      const data = JSON.parse(evt.data);
      onEvent(data);
    } catch {
      // ignore parse failure on pings
    }
  };

  eventSource.addEventListener("Connected", handleMessage);
  eventSource.addEventListener("GateDecisionChanged", handleMessage);
  eventSource.addEventListener("SaleSubmitted", handleMessage);
  eventSource.addEventListener("CancellationRequested", handleMessage);
  eventSource.addEventListener("Notification", handleMessage);

  return () => {
    eventSource.close();
  };
}
