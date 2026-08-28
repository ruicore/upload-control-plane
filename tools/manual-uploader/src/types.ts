export type UploadTaskCreateRequest = {
  task_name: string;
  task_initiator: "web";
  objects: Array<{
    dataset_name: string;
    object_name: string;
    file_size_bytes: number;
    content_type?: string;
    part_size_bytes: number;
    metadata: Record<string, unknown>;
  }>;
  metadata: Record<string, unknown>;
};

export type UploadTaskCreateResponse = {
  task_id: string;
  project_id: string;
  status: string;
  object_count: number;
  total_size_bytes: number;
  objects: Array<{
    object_id: string;
    dataset_id: string;
    session_id: string;
    status: string;
    object_name: string;
    bucket: string;
    object_key: string;
    file_size_bytes: number;
    part_size_bytes: number;
    part_count: number;
    expires_at: string;
  }>;
  created_at: string;
};

export type UploadSessionStatusResponse = {
  session_id: string;
  project_id: string | null;
  dataset_id: string | null;
  status: string;
  bucket: string;
  object_key: string;
  original_filename: string;
  file_size_bytes: number;
  part_size_bytes: number;
  part_count: number;
  uploaded_part_count: number;
  missing_part_count: number;
  paused_at: string | null;
  pause_reason: string | null;
  expires_at: string;
  created_at: string;
  updated_at: string;
};

export type PresignedPart = {
  part_number: number;
  url: string;
  expected_size_bytes: number;
  offset_start: number;
  offset_end_exclusive: number;
  required_headers: Record<string, string>;
};

export type PresignPartsResponse = {
  session_id: string;
  method: "PUT";
  expires_at: string;
  parts: PresignedPart[];
};

export type UploadedPart = {
  partNumber: number;
  etag: string;
  sizeBytes: number;
};

export type ListPartsResponse = {
  session_id: string;
  source: "db" | "storage" | "reconcile";
  part_count: number;
  uploaded_part_count: number;
  missing_part_numbers: number[];
  parts: Array<{
    part_number: number;
    etag: string | null;
    size_bytes: number | null;
    status: string;
    uploaded_at: string | null;
    expected_size_bytes: number;
    offset_start: number;
    offset_end_exclusive: number;
    last_presigned_at: string | null;
    presign_expires_at: string | null;
  }>;
};
