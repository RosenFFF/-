import { errorText } from "../api/errors";
export function ErrorNotice({ error }: { error: unknown }) {
  return error ? (
    <div role="alert" className="banner error-notice">
      {errorText(error)}
    </div>
  ) : null;
}
