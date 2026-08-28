import { describe, expect, it } from "vitest";

import { getFilePart, getPartCount, MIB, parsePartSizeMiB } from "../fileParts";

describe("file part helpers", () => {
  it("rejects part sizes below the S3 multipart minimum", () => {
    expect(() => parsePartSizeMiB("4")).toThrow(/at least 5 MiB/);
  });

  it("calculates first and final byte ranges", () => {
    const fileSize = 13 * MIB;
    const partSize = 5 * MIB;

    expect(getPartCount(fileSize, partSize)).toBe(3);
    expect(getFilePart(fileSize, partSize, 1)).toEqual({
      partNumber: 1,
      offsetStart: 0,
      offsetEndExclusive: 5 * MIB,
      sizeBytes: 5 * MIB
    });
    expect(getFilePart(fileSize, partSize, 3)).toEqual({
      partNumber: 3,
      offsetStart: 10 * MIB,
      offsetEndExclusive: 13 * MIB,
      sizeBytes: 3 * MIB
    });
  });
});
