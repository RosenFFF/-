/** DEMO_MODE-only audit tamper/restore. Never imported from the production client graph. */
import { body, json } from "./http";
import type { DemoRestoreResult, DemoTamperResult } from "./types";

const id = encodeURIComponent;

export const demoAuditApi = {
  tamper(logId: string): Promise<DemoTamperResult> {
    return json("/demo/audit/tamper", {
      method: "POST",
      ...body({ log_id: id(logId) }),
    });
  },
  restore(logId: string): Promise<DemoRestoreResult> {
    return json("/demo/audit/restore", {
      method: "POST",
      ...body({ log_id: id(logId) }),
    });
  },
};
