export function redactPresignedUrl(value: string): string {
  try {
    const parsed = new URL(value);
    parsed.search = "";
    parsed.hash = "";
    return parsed.toString();
  } catch {
    const queryStart = value.indexOf("?");
    return queryStart >= 0 ? value.slice(0, queryStart) : value;
  }
}

export function redactDiagnosticValue(value: unknown): unknown {
  if (typeof value === "string") {
    return maybeRedactString(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => redactDiagnosticValue(item));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, nested]) => [
        key,
        key.toLowerCase() === "url"
          ? redactDiagnosticValue(String(nested))
          : redactDiagnosticValue(nested)
      ])
    );
  }
  return value;
}

function maybeRedactString(value: string): string {
  if (value.includes("X-Amz-") || value.includes("uploadId=") || value.includes("partNumber=")) {
    return redactPresignedUrl(value);
  }
  return value;
}
