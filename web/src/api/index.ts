import type { Api } from "./types";
import { realApi } from "./real";
// Mock is opt-in AND dev-only. Production builds cannot present mock results as real.
export const useMock =
  import.meta.env.DEV && import.meta.env.VITE_USE_MOCK === "true";
export const api: Api = useMock
  ? (await import("../mock/api")).mockApi
  : realApi;
