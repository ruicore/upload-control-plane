import { firstCreatedObject, uploadMissingParts } from "./browserMultipartUploader";
import { ControlPlaneClient } from "./controlPlaneClient";
import { getPartCount, parsePartSizeMiB } from "./fileParts";
import { redactDiagnosticValue, redactPresignedUrl } from "./redaction";
import type {
  ListPartsResponse,
  UploadedPart,
  UploadSessionStatusResponse,
  UploadTaskCreateRequest,
  UploadTaskCreateResponse
} from "./types";
import "./styles.css";

type CurrentUpload = {
  file: File;
  task: UploadTaskCreateResponse;
  session: UploadSessionStatusResponse;
  uploadedParts: Map<number, UploadedPart>;
};

type FormValues = {
  apiUrl: string;
  apiKey: string;
  projectId: string;
  taskName: string;
  datasetName: string;
  objectName: string;
  contentType: string;
  partSizeMiB: string;
  concurrency: number;
  expiresInSeconds: number;
  shouldAck: boolean;
  objectMetadata: string;
  taskMetadata: string;
};

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) throw new Error("App mount point missing.");

let currentUpload: CurrentUpload | null = null;
let selectedFile: File | null = null;
let pausedLocally = false;

app.innerHTML = `
  <section class="shell">
    <header class="topbar">
      <div><p class="eyebrow">Development tool</p><h1>Manual Multipart Upload Verification</h1></div>
      <div class="status-pill" id="connectionStatus">No session</div>
    </header>
    <section class="workspace">
      <form class="panel form-grid" id="uploadForm">
        <label>API URL<input name="apiUrl" value="http://localhost:18080" autocomplete="off" /></label>
        <label>API key<input name="apiKey" type="password" autocomplete="off" /></label>
        <label>Project ID<input name="projectId" autocomplete="off" /></label>
        <label>File<input name="file" type="file" /></label>
        <label>Task name<input name="taskName" value="manual-browser-upload" autocomplete="off" /></label>
        <label>Dataset name<input name="datasetName" value="manual-browser-dataset" autocomplete="off" /></label>
        <label>Object name<input name="objectName" placeholder="Uses selected filename when empty" autocomplete="off" /></label>
        <label>Content type<input name="contentType" placeholder="Uses selected file type when empty" autocomplete="off" /></label>
        <label>Part size MiB<input name="partSizeMiB" type="number" min="5" step="1" value="5" /></label>
        <label>Concurrency<input name="concurrency" type="number" min="1" max="64" step="1" value="4" /></label>
        <label>Presign expiry seconds<input name="expiresInSeconds" type="number" min="1" step="1" value="900" /></label>
        <label class="checkbox-row"><input name="shouldAck" type="checkbox" checked />Ack each successful part</label>
        <label class="wide">Object metadata JSON<textarea name="objectMetadata" rows="4">{}</textarea></label>
        <label class="wide">Task metadata JSON<textarea name="taskMetadata" rows="4">{"tool":"manual-uploader"}</textarea></label>
        <div class="actions wide">
          <button type="button" id="createTaskButton">Create Task</button>
          <button type="button" id="uploadButton">Upload Missing Parts</button>
          <button type="button" id="completeButton">Complete</button>
          <button type="button" id="pauseButton">Pause</button>
          <button type="button" id="resumeButton">Resume</button>
          <button type="button" id="statusButton">Status</button>
          <button type="button" id="reconcileButton">Reconcile Parts</button>
          <button type="button" class="danger" id="abortButton">Abort</button>
        </div>
      </form>
      <aside class="panel side-panel">
        <h2>Current Session</h2><dl id="sessionSummary" class="summary"></dl>
        <h2>Progress</h2><div class="progress-shell"><div id="progressBar" class="progress-bar"></div></div>
        <p id="progressText" class="muted">No upload started.</p>
      </aside>
    </section>
    <section class="panel diagnostics">
      <div class="diagnostics-header"><h2>Diagnostics</h2><button type="button" id="clearLogButton">Clear</button></div>
      <pre id="log"></pre>
    </section>
  </section>
`;

const uploadForm = query<HTMLFormElement>("#uploadForm");
const logElement = query<HTMLPreElement>("#log");
const sessionSummary = query<HTMLElement>("#sessionSummary");
const progressBar = query<HTMLElement>("#progressBar");
const progressText = query<HTMLElement>("#progressText");
const connectionStatus = query<HTMLElement>("#connectionStatus");
const fileInput = uploadForm.elements.namedItem("file") as HTMLInputElement;

fileInput.addEventListener("change", () => {
  selectedFile = fileInput.files?.[0] ?? null;
  if (!selectedFile) return;
  const objectNameInput = uploadForm.elements.namedItem("objectName") as HTMLInputElement;
  const contentTypeInput = uploadForm.elements.namedItem("contentType") as HTMLInputElement;
  if (!objectNameInput.value) objectNameInput.value = selectedFile.name;
  if (!contentTypeInput.value && selectedFile.type) contentTypeInput.value = selectedFile.type;
  log("file.selected", {
    name: selectedFile.name,
    size: selectedFile.size,
    type: selectedFile.type || "application/octet-stream"
  });
});

bind("#createTaskButton", createTask);
bind("#uploadButton", uploadParts);
bind("#completeButton", completeUpload);
bind("#pauseButton", pauseUpload);
bind("#resumeButton", resumeUpload);
bind("#statusButton", refreshStatus);
bind("#reconcileButton", reconcileParts);
bind("#abortButton", abortUpload);
bind("#clearLogButton", clearLocalState);

function bind(selector: string, handler: () => Promise<void> | void): void {
  query<HTMLButtonElement>(selector).addEventListener("click", () => {
    void runAction(handler);
  });
}

async function runAction(handler: () => Promise<void> | void): Promise<void> {
  try {
    await handler();
  } catch (error) {
    log("error", normalizeError(error));
  }
}

async function createTask(): Promise<void> {
  const file = requireSelectedFile();
  const values = formValues();
  const client = clientFrom(values);
  const partSizeBytes = parsePartSizeMiB(values.partSizeMiB);
  const request: UploadTaskCreateRequest = {
    task_name: values.taskName,
    task_initiator: "web",
    objects: [
      {
        dataset_name: values.datasetName,
        object_name: values.objectName || file.name,
        file_size_bytes: file.size,
        content_type: values.contentType || file.type || "application/octet-stream",
        part_size_bytes: partSizeBytes,
        metadata: parseJsonObject(values.objectMetadata, "Object metadata")
      }
    ],
    metadata: parseJsonObject(values.taskMetadata, "Task metadata")
  };
  const response = await client.createUploadTask(values.projectId, request, idempotencyKey("create"));
  const createdObject = firstCreatedObject(response);
  const session = await client.getSession(createdObject.session_id);
  currentUpload = { file, task: response, session, uploadedParts: new Map() };
  pausedLocally = false;
  renderSession(session);
  updateProgress(0, session.part_count, 0, file.size);
  log("task.created", response);
}

async function uploadParts(): Promise<void> {
  const upload = requireCurrentUpload();
  const values = formValues();
  const client = clientFrom(values);
  pausedLocally = false;
  const result = await uploadMissingParts({
    file: upload.file,
    client,
    sessionId: upload.session.session_id,
    partCount: upload.session.part_count,
    concurrency: values.concurrency,
    expiresInSeconds: values.expiresInSeconds,
    shouldAck: values.shouldAck,
    alreadyUploadedParts: upload.uploadedParts,
    shouldContinue: () => !pausedLocally,
    onProgress: (progress) => {
      updateProgress(progress.uploadedParts, progress.totalParts, progress.uploadedBytes, progress.totalBytes);
      log("part.uploaded", {
        part_number: progress.currentPart,
        uploaded_parts: progress.uploadedParts,
        total_parts: progress.totalParts
      });
    }
  });
  upload.uploadedParts = new Map(result.uploadedParts.map((part) => [part.partNumber, part]));
  await refreshStatus();
}

async function completeUpload(): Promise<void> {
  const upload = requireCurrentUpload();
  const result = await clientFrom(formValues()).complete(
    upload.session.session_id,
    idempotencyKey("complete"),
    Array.from(upload.uploadedParts.values())
  );
  log("session.completed", result);
  await refreshStatus();
}

async function pauseUpload(): Promise<void> {
  const upload = requireCurrentUpload();
  pausedLocally = true;
  const result = await clientFrom(formValues()).pause(upload.session.session_id, idempotencyKey("pause"));
  log("session.paused", result);
  await refreshStatus();
}

async function resumeUpload(): Promise<void> {
  const upload = requireCurrentUpload();
  pausedLocally = false;
  const result = await clientFrom(formValues()).resume(upload.session.session_id, idempotencyKey("resume"));
  log("session.resumed", result);
  await refreshStatus();
  await uploadParts();
}

async function refreshStatus(): Promise<void> {
  const upload = requireCurrentUpload();
  upload.session = await clientFrom(formValues()).getSession(upload.session.session_id);
  renderSession(upload.session);
  log("session.status", upload.session);
}

async function reconcileParts(): Promise<void> {
  const upload = requireCurrentUpload();
  const result = await clientFrom(formValues()).listParts(upload.session.session_id, "reconcile");
  mergeUploadedParts(upload, result);
  log("parts.reconciled", result);
  await refreshStatus();
}

async function abortUpload(): Promise<void> {
  const upload = requireCurrentUpload();
  pausedLocally = true;
  const result = await clientFrom(formValues()).abort(upload.session.session_id, idempotencyKey("abort"));
  log("session.aborted", result);
  await refreshStatus();
}

function clearLocalState(): void {
  currentUpload = null;
  pausedLocally = false;
  connectionStatus.textContent = "No session";
  sessionSummary.innerHTML = "";
  progressBar.style.width = "0%";
  progressText.textContent = "No upload started.";
  logElement.textContent = "";
}

function mergeUploadedParts(upload: CurrentUpload, result: ListPartsResponse): void {
  for (const part of result.parts) {
    if (part.etag && part.size_bytes) {
      upload.uploadedParts.set(part.part_number, {
        partNumber: part.part_number,
        etag: part.etag,
        sizeBytes: part.size_bytes
      });
    }
  }
}

function formValues(): FormValues {
  const formData = new FormData(uploadForm);
  return {
    apiUrl: requireString(formData, "apiUrl"),
    apiKey: requireString(formData, "apiKey"),
    projectId: requireString(formData, "projectId"),
    taskName: requireString(formData, "taskName"),
    datasetName: requireString(formData, "datasetName"),
    objectName: String(formData.get("objectName") ?? ""),
    contentType: String(formData.get("contentType") ?? ""),
    partSizeMiB: requireString(formData, "partSizeMiB"),
    concurrency: clampNumber(requireString(formData, "concurrency"), 1, 64, "Concurrency"),
    expiresInSeconds: clampNumber(requireString(formData, "expiresInSeconds"), 1, 21600, "Expiry"),
    shouldAck: formData.get("shouldAck") === "on",
    objectMetadata: requireString(formData, "objectMetadata"),
    taskMetadata: requireString(formData, "taskMetadata")
  };
}

function clientFrom(values: FormValues): ControlPlaneClient {
  return new ControlPlaneClient({ apiUrl: values.apiUrl, apiKey: values.apiKey });
}

function requireSelectedFile(): File {
  if (!selectedFile) throw new Error("Choose a file first.");
  return selectedFile;
}

function requireCurrentUpload(): CurrentUpload {
  if (!currentUpload) throw new Error("Create an upload task first.");
  return currentUpload;
}

function requireString(formData: FormData, name: string): string {
  const value = String(formData.get(name) ?? "").trim();
  if (!value) throw new Error(`${name} is required.`);
  return value;
}

function clampNumber(input: string, min: number, max: number, label: string): number {
  const value = Number(input);
  if (!Number.isInteger(value) || value < min || value > max) {
    throw new Error(`${label} must be an integer from ${min} to ${max}.`);
  }
  return value;
}

function parseJsonObject(input: string, label: string): Record<string, unknown> {
  const parsed = JSON.parse(input) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}

function renderSession(session: UploadSessionStatusResponse): void {
  connectionStatus.textContent = session.status;
  sessionSummary.innerHTML = `
    <dt>Session</dt><dd>${session.session_id}</dd>
    <dt>Project</dt><dd>${session.project_id ?? "n/a"}</dd>
    <dt>Dataset</dt><dd>${session.dataset_id ?? "n/a"}</dd>
    <dt>Object</dt><dd>${session.bucket}/${session.object_key}</dd>
    <dt>File</dt><dd>${session.original_filename}</dd>
    <dt>Parts</dt><dd>${session.uploaded_part_count}/${session.part_count}</dd>
    <dt>Expires</dt><dd>${session.expires_at}</dd>
  `;
  updateProgress(
    session.uploaded_part_count,
    getPartCount(session.file_size_bytes, session.part_size_bytes),
    0,
    session.file_size_bytes
  );
}

function updateProgress(uploadedParts: number, totalParts: number, uploadedBytes: number, totalBytes: number): void {
  const percent = totalParts === 0 ? 0 : Math.round((uploadedParts / totalParts) * 100);
  progressBar.style.width = `${percent}%`;
  const bytesText = uploadedBytes > 0 ? `, ${formatBytes(uploadedBytes)} / ${formatBytes(totalBytes)}` : "";
  progressText.textContent = `${uploadedParts} / ${totalParts} parts${bytesText}`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GiB`;
}

function log(event: string, details: unknown): void {
  const line = JSON.stringify(
    { time: new Date().toISOString(), event, details: redactDiagnosticValue(details) },
    null,
    2
  );
  logElement.textContent = `${line}\n${logElement.textContent}`;
}

function normalizeError(error: unknown): unknown {
  if (error instanceof Error) {
    return {
      name: error.name,
      message: redactPresignedUrl(error.message),
      body: "body" in error ? redactDiagnosticValue((error as { body: unknown }).body) : undefined
    };
  }
  return redactDiagnosticValue(error);
}

function idempotencyKey(action: string): string {
  return `manual-uploader-${action}-${crypto.randomUUID()}`;
}

function query<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Missing element: ${selector}`);
  return element;
}
