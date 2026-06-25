# Manual Uploader

Development-only browser verification tool for the multipart upload control plane.

It runs as a separate Vite app on `http://localhost:5173` so local browser uploads exercise real CORS behavior. The tool calls only public control-plane APIs and sends file bytes only through presigned object-storage `PUT` requests.

```bash
npm install
npm run dev
```

From the repository root:

```bash
make manual-uploader
```

The UI keeps upload state in memory for diagnostics. It does not write presigned URLs to `localStorage`, `sessionStorage`, or files, and visible diagnostics redact presigned URL query strings.
