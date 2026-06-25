export const MIB = 1024 * 1024;
export const MIN_PART_SIZE_BYTES = 5 * MIB;

export type FilePart = {
  partNumber: number;
  offsetStart: number;
  offsetEndExclusive: number;
  sizeBytes: number;
};

export function parsePartSizeMiB(input: string): number {
  const value = Number(input);
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error("Part size must be a positive number of MiB.");
  }
  const bytes = Math.trunc(value * MIB);
  if (bytes < MIN_PART_SIZE_BYTES) {
    throw new Error("Part size must be at least 5 MiB for multipart upload.");
  }
  return bytes;
}

export function getPartCount(fileSizeBytes: number, partSizeBytes: number): number {
  if (!Number.isInteger(fileSizeBytes) || fileSizeBytes <= 0) {
    throw new Error("File size must be positive.");
  }
  if (!Number.isInteger(partSizeBytes) || partSizeBytes <= 0) {
    throw new Error("Part size must be positive.");
  }
  return Math.ceil(fileSizeBytes / partSizeBytes);
}

export function getFilePart(
  fileSizeBytes: number,
  partSizeBytes: number,
  partNumber: number
): FilePart {
  const partCount = getPartCount(fileSizeBytes, partSizeBytes);
  if (!Number.isInteger(partNumber) || partNumber < 1 || partNumber > partCount) {
    throw new Error(`Part number must be in range 1..${partCount}.`);
  }
  const offsetStart = (partNumber - 1) * partSizeBytes;
  const offsetEndExclusive = Math.min(offsetStart + partSizeBytes, fileSizeBytes);
  return {
    partNumber,
    offsetStart,
    offsetEndExclusive,
    sizeBytes: offsetEndExclusive - offsetStart
  };
}

export function allPartNumbers(partCount: number): number[] {
  if (!Number.isInteger(partCount) || partCount < 1) {
    throw new Error("Part count must be a positive integer.");
  }
  return Array.from({ length: partCount }, (_, index) => index + 1);
}
