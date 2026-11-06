import { describe, expect, it } from "vitest";
import i18n from "../i18n";
import { errorCodes, errorText } from "./errors";
import { ApiError } from "./http";
describe("safe error-code i18n", () => {
  it.each(["zh", "en", "vi"])(
    "%s covers every contract and transport code",
    async (lang) => {
      await i18n.changeLanguage(lang);
      for (const code of errorCodes) {
        expect(
          i18n.getResource(lang, "translation", `errors.${code}`),
        ).toBeTruthy();
        const text = errorText(
          new ApiError({ code, status: 400, request_id: "rid-123" }),
        );
        expect(text).not.toContain(`errors.${code}`);
        expect(text).toContain("rid-123");
        expect(text.length).toBeGreaterThan(15);
      }
    },
  );
  it("does not expose unknown codes or server detail", () => {
    const text = errorText(new ApiError({ code: "SECRET_STACK", status: 500 }));
    expect(text).not.toContain("SECRET_STACK");
    expect(text).toBe(i18n.t("errors.INTERNAL_ERROR"));
  });
});

describe("501 is explicitly not implemented, even with an old backend code", () => {
  it.each([
    ["zh", "功能暂未实现"],
    ["en", "Not implemented yet"],
    ["vi", "Tính năng chưa được triển khai"],
  ])("%s uses the exact approved wording", async (lang, text) => {
    await i18n.changeLanguage(lang);
    expect(
      errorText(new ApiError({ status: 501, code: "MODEL_UNAVAILABLE" })),
    ).toBe(text);
    expect(
      errorText(new ApiError({ status: 501, code: "NOT_IMPLEMENTED" })),
    ).toBe(text);
  });
});
