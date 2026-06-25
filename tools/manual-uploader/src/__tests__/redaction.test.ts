import { describe, expect, it } from "vitest";

import { redactDiagnosticValue, redactPresignedUrl } from "../redaction";

describe("presigned URL redaction", () => {
  it("removes query strings from URL diagnostics", () => {
    expect(
      redactPresignedUrl(
        "http://localhost:19000/robot-data/object.bin?partNumber=1&uploadId=abc&X-Amz-Signature=secret"
      )
    ).toBe("http://localhost:19000/robot-data/object.bin");
  });

  it("recursively redacts nested presigned part URLs", () => {
    expect(
      redactDiagnosticValue({
        parts: [
          {
            part_number: 1,
            url: "http://localhost:19000/b/key?X-Amz-Signature=secret"
          }
        ]
      })
    ).toEqual({
      parts: [
        {
          part_number: 1,
          url: "http://localhost:19000/b/key"
        }
      ]
    });
  });
});
