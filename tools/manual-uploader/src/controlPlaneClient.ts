import type {
  ListPartsResponse,
  PresignPartsResponse,
  UploadedPart,
  UploadSessionStatusResponse,
  UploadTaskCreateRequest,
  UploadTaskCreateResponse
} from "./types";

type ClientOptions = {
  apiUrl: string;
  apiKey: string;
};

export class ControlPlaneClient {
  private readonly apiUrl: string;
  private readonly apiKey: string;

  constructor(options: ClientOptions) {
    this.apiUrl = options.apiUrl.replace(/\/+$/, "");
    this.apiKey = options.apiKey;
  }

  async createUploadTask(
    projectId: string,
    request: UploadTaskCreateRequest,
    idempotencyKey: string
  ): Promise<UploadTaskCreateResponse> {
    return this.request<UploadTaskCreateResponse>(
      `/v1/projects/${encodeURIComponent(projectId)}/upload-tasks`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey
        },
        body: JSON.stringify(request)
      }
    );
  }

  async getSession(sessionId: string): Promise<UploadSessionStatusResponse> {
    return this.request<UploadSessionStatusResponse>(`/v1/uploads/${encodeURIComponent(sessionId)}`);
  }

  async presignParts(
    sessionId: string,
    partNumbers: number[],
    expiresInSeconds: number
  ): Promise<PresignPartsResponse> {
    return this.request<PresignPartsResponse>(
      `/v1/uploads/${encodeURIComponent(sessionId)}/parts/presign`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          part_numbers: partNumbers,
          expires_in_seconds: expiresInSeconds
        })
      }
    );
  }

  async ackParts(sessionId: string, parts: UploadedPart[]): Promise<unknown> {
    return this.request(`/v1/uploads/${encodeURIComponent(sessionId)}/parts/ack`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        parts: parts.map((part) => ({
          part_number: part.partNumber,
          etag: part.etag,
          size_bytes: part.sizeBytes
        }))
      })
    });
  }

  async listParts(sessionId: string, source: "db" | "storage" | "reconcile"): Promise<ListPartsResponse> {
    return this.request<ListPartsResponse>(
      `/v1/uploads/${encodeURIComponent(sessionId)}/parts?source=${source}`
    );
  }

  async pause(sessionId: string, idempotencyKey: string): Promise<unknown> {
    return this.lifecycle(sessionId, "pause", idempotencyKey, {
      reason: "manual_uploader",
      client_inflight_behavior: "allow_finish"
    });
  }

  async resume(sessionId: string, idempotencyKey: string): Promise<unknown> {
    return this.lifecycle(sessionId, "resume", idempotencyKey, { reason: "manual_uploader" });
  }

  async complete(sessionId: string, idempotencyKey: string, parts: UploadedPart[]): Promise<unknown> {
    return this.lifecycle(sessionId, "complete", idempotencyKey, {
      client_reported_parts: parts.map((part) => ({
        part_number: part.partNumber,
        etag: part.etag
      }))
    });
  }

  async abort(sessionId: string, idempotencyKey: string): Promise<unknown> {
    return this.lifecycle(sessionId, "abort", idempotencyKey, { reason: "manual_uploader" });
  }

  private async lifecycle(
    sessionId: string,
    action: "pause" | "resume" | "complete" | "abort",
    idempotencyKey: string,
    body: Record<string, unknown>
  ): Promise<unknown> {
    return this.request(`/v1/uploads/${encodeURIComponent(sessionId)}/${action}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey
      },
      body: JSON.stringify(body)
    });
  }

  private async request<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${this.apiUrl}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        ...(init.headers ?? {})
      }
    });
    const contentType = response.headers.get("content-type") ?? "";
    const body = contentType.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      throw new ApiRequestError(response.status, body);
    }
    return body as T;
  }
}

export class ApiRequestError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown
  ) {
    super(`API request failed with HTTP ${status}.`);
  }
}
