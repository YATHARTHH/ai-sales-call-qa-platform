let currentTenantId = "retailer-cimet-01";
let currentUserId = "dev-auditor-01";

export function setTenantId(tenantId: string) {
  currentTenantId = tenantId;
}

export function getTenantId(): string {
  return currentTenantId;
}

export async function apiClient<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("X-Debug-Tenant-Id", currentTenantId);
  headers.set("X-Debug-User-Id", currentUserId);

  const response = await fetch(endpoint, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status} ${response.statusText}`;
    try {
      const errorJson = await response.json();
      if (errorJson.detail) {
        errorDetail = errorJson.detail;
      } else if (errorJson.error?.message) {
        errorDetail = errorJson.error.message;
      }
    } catch {
      // ignore parse failure
    }
    throw new Error(errorDetail);
  }

  return response.json();
}
