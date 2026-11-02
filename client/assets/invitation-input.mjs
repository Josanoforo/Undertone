const SESSION_ID = /^[a-f0-9]{32}$/i;
const JOIN_CODE = /^[A-Za-z0-9_-]{12}$/;

function failure(message) {
  return { ok: false, error: message };
}

function decodeComponent(raw) {
  try { return decodeURIComponent(raw.replace(/\+/g, " ")); }
  catch { return null; }
}

function parseQuery(raw) {
  const entries = [];
  const seen = new Set();
  if (!raw) return failure("The invitation link has no complete query pair.");
  for (const part of raw.split("&")) {
    if (!part) return failure("The invitation link is incomplete or truncated.");
    const equal = part.indexOf("=");
    if (equal < 0) return failure("The invitation link is missing a value pair.");
    const key = decodeComponent(part.slice(0, equal));
    const value = decodeComponent(part.slice(equal + 1));
    if (key === null || value === null) return failure("The invitation link contains malformed encoding.");
    if (seen.has(key)) return failure("The invitation link repeats a parameter; ask the creator for a fresh link.");
    seen.add(key);
    entries.push([key, value]);
  }
  const ids = entries.filter(([key]) => key === "sessionId").map(([, value]) => value);
  const codes = entries.filter(([key]) => key === "joinCode").map(([, value]) => value);
  if (ids.length > 1 || codes.length > 1) return failure("The invitation link repeats its session ID or code; ask the creator for a fresh link.");
  if (ids.length !== 1 || codes.length !== 1 || !ids[0] || !codes[0]) return failure("The invitation link is missing its complete session ID and code pair.");
  if (!SESSION_ID.test(ids[0]) || !JOIN_CODE.test(codes[0]) || /\.\.\.|…/.test(ids[0] + codes[0])) return failure("The invitation link appears incomplete or truncated; ask the creator for a fresh invitation.");
  return { ok: true, sessionId: ids[0], joinCode: codes[0] };
}

function parseUrl(raw) {
  if (!/^https?:\/\//i.test(raw) || /[\s#\\]/.test(raw)) return failure("Paste one complete HTTP or HTTPS invitation link without a fragment.");
  const match = raw.match(/^(https?):\/\/([^/?#]+)(\/[^?#]*)?\?([^#]*)$/i);
  if (!match || !match[2] || /\.\./.test(match[2]) || /[@%]/.test(match[2])) return failure("The invitation link is malformed or incomplete; ask the creator for the full link.");
  const authority = match[2].startsWith("[")
    ? match[2].match(/^(\[[^\]]+\])(?::(\d+))?$/)
    : match[2].match(/^([^:]+)(?::(\d+))?$/);
  if (!authority) return failure("The invitation link has an invalid host or port; ask the creator for the full link.");
  const rawHostname = authority[1];
  let parsed;
  try { parsed = new URL(raw); }
  catch { return failure("The invitation link has an invalid host or port; ask the creator for the full link."); }
  if (parsed.protocol !== `${match[1].toLowerCase()}:` || !parsed.hostname || parsed.hostname.toLowerCase() !== rawHostname.toLowerCase() || parsed.username || parsed.password) {
    return failure("The invitation link has an invalid host or contains sign-in details; ask the creator for the full link.");
  }
  return parseQuery(match[4]);
}

export function parseInvitationText(input) {
  if (typeof input !== "string" || !input) return failure("Paste a complete invitation link or the complete session ID and code block.");
  const text = input;
  if (text.includes("...") || text.includes("…")) return failure("The invitation appears truncated. Copy the complete invitation again.");
  if (text.startsWith("#") || (!/^https?:\/\//i.test(text) && text.includes("#"))) return failure("A fragment is not an invitation link. Paste the complete link including its session ID and code.");
  const markdown = text.match(/^\[([^\]\r\n]+)\]\((https?:\/\/[^\s()]*)\)$/i);
  if (markdown) return parseUrl(markdown[2]);
  if (/^\[[^\]]*\]\(/.test(text) || /\]\([^)]*$/.test(text)) return failure("The Markdown invitation link is incomplete. Copy the complete link again.");
  if (/^https?:\/\//i.test(text)) return parseUrl(text);
  if (/https?:/i.test(text)) return failure("The invitation link is incomplete. Copy the complete HTTP or HTTPS link again.");
  const lines = text.split(/\r?\n/);
  if (lines.length === 3 && /^Session ID: /.test(lines[0]) && /^Invitation code: /.test(lines[1]) && lines[2] === "A public viewer address is not configured.") {
    const sessionId = lines[0].slice("Session ID: ".length);
    const joinCode = lines[1].slice("Invitation code: ".length);
    if (!sessionId || !joinCode || !SESSION_ID.test(sessionId) || !JOIN_CODE.test(joinCode) || /\.\.\.|…/.test(text)) return failure("The copied invitation block is incomplete or truncated.");
    return { ok: true, sessionId, joinCode };
  }
  if (lines.some(line => /^(?:Session ID|Invitation code)\s*:/i.test(line))) return failure("The copied invitation block is incomplete. Copy all invitation lines from the creator.");
  if (hasInvitationMarkers(text)) return failure("Invitation text contains mixed or partial link details. Paste the complete invitation link or the creator’s complete ID and code block.");
  return failure("Unrecognized invitation. Paste a complete invitation link or the creator’s complete ID and code block.");
}

function hasInvitationMarkers(input) {
  if (typeof input !== "string") return false;
  const decoded = decodeComponent(input);
  const candidates = decoded === null ? [input] : [input, decoded];
  return candidates.some(text =>
    /https?:/i.test(text) ||
    /(?:^|[?&#])\s*(?:sessionId|joinCode)\s*=/i.test(text) ||
    /(?:^|[?&#])(?:%[0-9a-f]{2}|\w){0,20}(?:sessionId|joinCode)(?:%[0-9a-f]{2}|\w){0,20}\s*=/i.test(text) ||
    /\[[^\]\r\n]*\]\s*\(/.test(text) || /\]\([^)]*$/.test(text) ||
    /^(?:Session ID|Invitation code)\s*:/im.test(text)
  );
}

export function parseInvitationSearch(search) {
  const raw = String(search || "").replace(/^\?/, "");
  if (!raw) return { present: false };
  const decodedKeys = raw.split("&").map(part => decodeComponent(part.split("=", 1)[0]));
  if (!decodedKeys.includes("sessionId") && !decodedKeys.includes("joinCode")) return { present: false };
  const result = parseQuery(raw);
  return { present: true, ...result };
}

export function looksLikeInvitation(input) {
  return hasInvitationMarkers(input);
}
