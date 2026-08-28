import type { ControlPlaneClient } from "./controlPlaneClient";
import { allPartNumbers } from "./fileParts";
import type { PresignedPart, UploadedPart, UploadTaskCreateResponse } from "./types";

export type UploadProgress = {
  currentPart: number;
  uploadedParts: number;
  totalParts: number;
  uploadedBytes: number;
  totalBytes: number;
};

export type MultipartUploadOptions = {
  file: File;
  client: ControlPlaneClient;
  sessionId: string;
  partCount: number;
  concurrency: number;
  expiresInSeconds: number;
  shouldAck: boolean;
  alreadyUploadedParts: Map<number, UploadedPart>;
  shouldContinue: () => boolean;
  onProgress: (progress: UploadProgress) => void;
};

export type MultipartUploadResult = {
  uploadedParts: UploadedPart[];
};

export function firstCreatedObject(response: UploadTaskCreateResponse) {
  const first = response.objects[0];
  if (!first) {
    throw new Error("Upload task response did not contain an upload object.");
  }
  return first;
}

export async function uploadMissingParts(
  options: MultipartUploadOptions
): Promise<MultipartUploadResult> {
  const uploadedParts = new Map(options.alreadyUploadedParts);
  const missingQueue = allPartNumbers(options.partCount).filter((partNumber) => !uploadedParts.has(partNumber));
  const workerCount = Math.max(1, Math.min(options.concurrency, missingQueue.length));
  let uploadedBytes = Array.from(uploadedParts.values()).reduce((sum, part) => sum + part.sizeBytes, 0);

  async function worker(): Promise<void> {
    while (options.shouldContinue()) {
      const partNumber = missingQueue.shift();
      if (partNumber === undefined) {
        return;
      }
      const presign = await options.client.presignParts(
        options.sessionId,
        [partNumber],
        options.expiresInSeconds
      );
      const part = presign.parts[0];
      if (!part) {
        throw new Error(`No presigned URL returned for part ${partNumber}.`);
      }
      const uploaded = await uploadPart(options.file, part);
      uploadedParts.set(uploaded.partNumber, uploaded);
      uploadedBytes += uploaded.sizeBytes;
      if (options.shouldAck) {
        await options.client.ackParts(options.sessionId, [uploaded]);
      }
      options.onProgress({
        currentPart: uploaded.partNumber,
        uploadedParts: uploadedParts.size,
        totalParts: options.partCount,
        uploadedBytes,
        totalBytes: options.file.size
      });
    }
  }

  await Promise.all(Array.from({ length: workerCount }, () => worker()));
  return { uploadedParts: Array.from(uploadedParts.values()).sort((a, b) => a.partNumber - b.partNumber) };
}

async function uploadPart(file: File, part: PresignedPart): Promise<UploadedPart> {
  const blob = file.slice(part.offset_start, part.offset_end_exclusive);
  const response = await fetch(part.url, {
    method: "PUT",
    headers: part.required_headers,
    body: blob
  });
  if (!response.ok) {
    throw new Error(`Storage PUT for part ${part.part_number} failed with HTTP ${response.status}.`);
  }
  const etag = response.headers.get("ETag");
  if (!etag) {
    throw new Error(`Storage PUT for part ${part.part_number} did not expose an ETag header.`);
  }
  return {
    partNumber: part.part_number,
    etag,
    sizeBytes: blob.size
  };
}
