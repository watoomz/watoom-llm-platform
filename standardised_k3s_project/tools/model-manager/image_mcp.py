"""Scoped MCP surface: installed image models, idempotent queue, status and PNGs.
No installation/removal, arbitrary paths, URLs, shell execution or admin password.
"""

import base64, hashlib, hmac, json, re, struct, time

KINDS = {"diffusion-pipeline", "diffusion-checkpoint", "lora"}
ID = re.compile(r"[a-f0-9]{64}")


def schema(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


STR = {"type": "string"}
GENERATION = {
    "width": {"type": "integer", "minimum": 256, "maximum": 1024, "multipleOf": 8},
    "height": {"type": "integer", "minimum": 256, "maximum": 1024, "multipleOf": 8},
    "steps": {"type": "integer", "minimum": 1, "maximum": 50},
    "guidance": {"type": "number", "minimum": 0, "maximum": 20},
    "seed": {"type": "integer", "minimum": 0, "maximum": 4294967295},
    "scheduler": {"type": "string", "enum": ["euler", "dpm"]},
}


def generation_settings(value):
    from settings import IMAGE, validate

    if not isinstance(value, dict) or set(value) - set(GENERATION):
        raise ValueError("Unsupported image generation setting")
    result = {k: IMAGE[k] for k in GENERATION}
    result.update(value)
    validate(result, "diffusion-pipeline")
    if result["width"] > 1024 or result["height"] > 1024 or result["steps"] > 50 or result["guidance"] > 20:
        raise ValueError("Image worker budget exceeded")
    return result


TOOLS = [
    {
        "name": "list_session_images",
        "description": "Read durable image receipts belonging to the calling native session. Never starts or resumes generation.",
        "inputSchema": schema({}),
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "list_image_models",
        "description": "List installed registered image models and their pinned revisions; does not load or install models.",
        "inputSchema": schema({}),
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "submit_image",
        "description": "Queue one image using an installed model and a stable request_id. Defaults: 1024 square, 30 steps, guidance 7. Validated per-job settings can override these; installed weights/runtime remain unchanged. Returns immediately. Finish this chat turn after submission: the GPU worker starts only after native work is idle, then restores the previous chat model. Do not poll in a tool loop or submit a second ID after uncertainty.",
        "inputSchema": schema(
            {
                "request_id": {**STR, "pattern": "^[A-Za-z0-9_-]{1,80}$"},
                "installation_id": {**STR, "pattern": "^[a-f0-9]{64}$"},
                "revision": {**STR, "pattern": "^[a-f0-9]{40,64}$"},
                "prompt": {**STR, "minLength": 1, "maxLength": 4096},
                "negative_prompt": {
                    **STR,
                    "maxLength": 4096,
                    "description": "Optional negative conditioning, separate from the positive prompt.",
                },
                "settings": schema(GENERATION),
            },
            ["request_id", "installation_id", "revision", "prompt"],
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
    },
    {
        "name": "image_job",
        "description": "Read this image interface's queued/terminal job status. WAITING_NATIVE_IDLE means finish the chat turn; do not retry generation.",
        "inputSchema": schema({"job_id": {**STR, "pattern": "^[a-f0-9]{64}$"}}, ["job_id"]),
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "image_result",
        "description": "Return the actual PNG only after image generation, integrity validation and chat-model restoration succeeded. No new generation.",
        "inputSchema": schema({"job_id": {**STR, "pattern": "^[a-f0-9]{64}$"}}, ["job_id"]),
        "annotations": {"readOnlyHint": True},
    },
]


def text(value):
    return {"content": [{"type": "text", "text": json.dumps(value)}], "structuredContent": value}


def arguments(name, args):
    tool = next((t for t in TOOLS if t["name"] == name), None)
    if not tool or not isinstance(args, dict):
        raise ValueError("Unknown image tool or invalid arguments")
    s = tool["inputSchema"]
    if set(args) - set(s["properties"]) or set(s["required"]) - set(args):
        raise ValueError("Unexpected or missing image arguments")
    for k, v in args.items():
        if k == "settings":
            generation_settings(v)
            continue
        if not isinstance(v, str):
            raise ValueError("Image arguments must be strings")
        p = s["properties"][k]
        if (
            (p.get("pattern") and not re.fullmatch(p["pattern"], v))
            or len(v) < p.get("minLength", 0)
            or len(v) > p.get("maxLength", 4096)
        ):
            raise ValueError("Invalid image argument: " + k)
    return args


def job(app, key):
    row = app.store.db.execute(
        "SELECT j.state,j.error,j.updated,j.result FROM jobs j JOIN image_requests r ON r.job_id=j.id WHERE j.id=?",
        (key,),
    ).fetchone()
    if not row:
        raise ValueError("Unknown image job")
    return row


def call(app, name, args, session_id=None):
    args = arguments(name, args)
    if session_id is not None and (
        not isinstance(session_id, str) or not re.fullmatch(r"ses_[A-Za-z0-9]{1,80}", session_id)
    ):
        raise ValueError("Invalid native session identity")
    if name == "list_session_images":
        if not session_id:
            raise ValueError("Native session identity required")
        rows = app.store.db.execute(
            "SELECT j.id,j.state,j.error,j.updated,j.stage FROM jobs j JOIN image_request_sessions r ON r.job_id=j.id WHERE r.session_id=? ORDER BY j.created DESC LIMIT 32",
            (session_id,),
        ).fetchall()
        return text(
            {"jobs": [{"job_id": a, "state": b, "stage": e, "error": c, "updated": d} for a, b, c, d, e in rows]}
        )
    if name == "list_image_models":
        rows = []
        for (raw,) in app.store.db.execute("SELECT record FROM models"):
            d = json.loads(raw)
            if d.get("registered") and d.get("kind") in KINDS:
                rows.append({k: d.get(k) for k in ["id", "revision", "repository", "kind", "settings", "tested"]})
        return text(
            {
                "models": rows,
                "safe_job_defaults": generation_settings({}),
                "handoff": "queued-until-native-idle",
                "automatic_session_resume": False,
            }
        )
    if name == "submit_image":
        if app.maintenance_file and app.maintenance_file.exists():
            raise ValueError("Image admission closed for maintenance")
        if not app.operations:
            raise ValueError("Image lifecycle worker unavailable")
        row = app.store.db.execute("SELECT record FROM models WHERE id=?", (args["installation_id"],)).fetchone()
        if not row:
            raise ValueError("Choose an installed image model from list_image_models")
        record = json.loads(row[0])
        if (
            record.get("kind") not in KINDS
            or not record.get("registered")
            or record.get("revision") != args["revision"]
        ):
            raise ValueError("Stale or non-image installation; refresh installed models")
        settings = generation_settings(args.get("settings", {}))
        selection = {
            "settings": settings,
            "operation": "generate",
            "id": args["installation_id"],
            "revision": args["revision"],
            "prompt": args["prompt"],
            "source": "opencode-images",
            "request_id": args["request_id"],
        }
        if "negative_prompt" in args:
            selection["negative_prompt"] = args["negative_prompt"]
        raw = json.dumps(selection, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode()).hexdigest()
        with app.lock, app.store.db:
            prior = app.store.db.execute(
                "SELECT r.digest,r.job_id,s.session_id FROM image_requests r LEFT JOIN image_request_sessions s ON s.job_id=r.job_id WHERE r.request_id=?",
                (args["request_id"],),
            ).fetchone()
            if prior:
                if prior[2] != session_id:
                    raise ValueError("request_id belongs to another session")
                if prior[0] != digest:
                    raise ValueError("request_id already binds different input; reconcile the existing job")
                key = prior[1]
            else:
                key = digest
                app.store.db.execute(
                    "INSERT INTO jobs(id,selection,state,updated,created) VALUES(?,?,?,?,?)",
                    (key, raw, "QUEUED", time.time(), time.time()),
                )
                app.store.db.execute("INSERT INTO image_requests VALUES(?,?,?)", (args["request_id"], digest, key))
                if session_id:
                    app.store.db.execute("INSERT INTO image_request_sessions VALUES(?,?)", (key, session_id))
        return text(
            {
                "job_id": key,
                "state": job(app, key)[0],
                "next": "Finish the chat turn. The image worker waits for native idle before GPU handoff. The verified result appears automatically in the originating chat; no further prompt is needed. Model Manager also retains the receipt.",
                "settings": {**record.get("settings", {}), **settings},
                "session_started": False,
                "manager_url": app.origin + app.prefix + "/",
            }
        )
    state, error, updated, raw = job(app, args["job_id"])
    if name == "image_job":
        stage = app.store.db.execute("SELECT stage FROM jobs WHERE id=?", (args["job_id"],)).fetchone()[0]
        return text(
            {
                "job_id": args["job_id"],
                "state": state,
                "stage": stage,
                "error": error,
                "updated": updated,
                "result_available": state == "GENERATION_VERIFIED",
            }
        )
    if state != "GENERATION_VERIFIED" or not raw:
        raise ValueError("Image is not verified yet; inspect image_job without resubmitting")
    result = json.loads(raw)
    if not result.get("restoration", {}).get("verified"):
        raise ValueError("Chat-model restoration receipt missing")
    png = base64.b64decode(result.get("png_base64", ""), validate=True)
    if (
        not 24 <= len(png) <= 16 * 1024 * 1024
        or png[:8] != bytes([137, 80, 78, 71, 13, 10, 26, 10])
        or hashlib.sha256(png).hexdigest() != result.get("sha256")
    ):
        raise ValueError("Stored PNG integrity mismatch")
    width, height = struct.unpack(">II", png[16:24])
    if width != result.get("width") or height != result.get("height"):
        raise ValueError("PNG dimensions differ from worker receipt")
    meta = {
        "job_id": args["job_id"],
        "sha256": result["sha256"],
        "width": width,
        "height": height,
        "restoration": result["restoration"],
        "published": result.get("published"),
        "generation_settings": result.get("generation_settings"),
    }
    return {
        "content": [
            {"type": "text", "text": json.dumps(meta)},
            {"type": "image", "mimeType": "image/png", "data": result["png_base64"]},
        ],
        "structuredContent": meta,
    }


def handle(handler, app):
    token = getattr(app, "image_mcp_token", None)
    if not token:
        return handler.send(404, {"error": "Not found"})
    if not hmac.compare_digest(handler.headers.get("Authorization", ""), "Bearer " + token):
        return handler.send(401, {"error": "Image interface authentication required"})
    if handler.headers.get("Origin") not in (None, app.origin):
        return handler.send(403, {"error": "Image interface origin rejected"})
    try:
        size = int(handler.headers.get("Content-Length", "0"))
        if not 0 < size <= 32768:
            raise ValueError("Invalid MCP request size")
        req = json.loads(handler.rfile.read(size))
        method = req.get("method")
        if req.get("jsonrpc") != "2.0" or not isinstance(method, str):
            raise ValueError("Invalid JSON-RPC")
        if "id" not in req:
            if method != "notifications/initialized":
                raise ValueError("Unsupported notification")
            handler.send_response(202)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        params = req.get("params", {})
        if not isinstance(params, dict):
            raise ValueError("Invalid params")
        if method == "initialize":
            version = params.get("protocolVersion")
            if version not in ("2024-11-05", "2025-03-26", "2025-11-25"):
                version = "2025-11-25"
            result = {
                "protocolVersion": version,
                "serverInfo": {"name": "watoom-images", "version": "1.0.0"},
                "capabilities": {"tools": {"listChanged": False}},
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            if not isinstance(params.get("_meta", {}), dict):
                raise ValueError("Invalid MCP metadata")
            try:
                result = call(
                    app,
                    params.get("name"),
                    params.get("arguments", {}),
                    params.get("_meta", {}).get("ai.opencode/sessionID"),
                )
            except (ValueError, KeyError, TypeError) as error:
                result = {"isError": True, "content": [{"type": "text", "text": str(error)[:200]}]}
        else:
            return handler.send(
                200, {"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32601, "message": "Method not found"}}
            )
        return handler.send(200, {"jsonrpc": "2.0", "id": req["id"], "result": result})
    except (ValueError, KeyError, TypeError):
        return handler.send(400, {"error": "Malformed image MCP request"})
