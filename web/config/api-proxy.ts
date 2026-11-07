// Server-side only: never expose this setting through a VITE_* client variable.
export function resolveApiProxyTarget(value: string | undefined): string {
  const target = value ?? "http://127.0.0.1:8000";
  let url: URL;
  try {
    url = new URL(target);
  } catch {
    throw new Error("ST143_API_PROXY_TARGET must be an HTTP(S) loopback origin");
  }
  if (
    target !== target.trim() ||
    !["http:", "https:"].includes(url.protocol) ||
    !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname) ||
    url.username || url.password ||
    url.pathname !== "/" || url.search || url.hash
  ) {
    // Do not echo a rejected value: it could contain a secret.
    throw new Error("ST143_API_PROXY_TARGET must be an HTTP(S) loopback origin without credentials, path, query or fragment");
  }
  return url.origin;
}
