"""Keep only visual frames and minimal action metadata, never network/body data."""
import json
import sys
import zipfile


def sanitize(source, destination):
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as dst:
        images = set()
        for name in src.namelist():
            if not name.endswith(".trace"):
                continue
            records = []
            for line in src.read(name).splitlines():
                item = json.loads(line)
                kind = item.get("type")
                if kind == "context-options":
                    safe = {k: item[k] for k in ("version", "type", "origin", "browserName", "platform", "wallTime", "monotonicTime", "contextId") if k in item}
                    safe["options"] = {}
                elif kind == "screencast-frame":
                    safe = {k: item[k] for k in ("type", "pageId", "sha1", "width", "height", "timestamp", "frameSwapWallTime") if k in item}
                    if item.get("sha1"):
                        images.add("resources/" + item["sha1"])
                elif kind in ("before", "after"):
                    safe = {k: item[k] for k in ("type", "callId", "startTime", "endTime", "pageId", "class", "method") if k in item}
                    if kind == "before":
                        safe["params"] = {}
                    if item.get("error"):
                        safe["error"] = {"name": "Error", "message": "Action failed; details omitted for privacy"}
                else:
                    continue
                records.append(json.dumps(safe, ensure_ascii=False))
            dst.writestr(name, "\n".join(records) + "\n")
            dst.writestr(name.removesuffix(".trace") + ".network", "")
        for name in images:
            if name in src.namelist() and name.endswith((".jpeg", ".jpg", ".png")):
                dst.writestr(name, src.read(name))


if __name__ == "__main__":
    sanitize(sys.argv[1], sys.argv[2])
