// Read-only, credential-bound preparation for tab-only resume.
// The host must still fence identity and atomically install the resulting scope.
export async function verifyResumeAccess({sessionId, credential, signal}, fetcher = fetch) {
  if (!sessionId || !credential || signal?.aborted) throw new Error('unavailable');
  const base = `/api/sessions/${encodeURIComponent(sessionId)}`;
  const options = {method:'GET', headers:{Authorization:`Bearer ${credential}`}, signal, cache:'no-store', credentials:'same-origin', redirect:'error'};
  const read = async path => {
    const response = await fetcher(path, options);
    if (!response.ok || signal?.aborted) throw new Error('unavailable');
    return response.json();
  };
  const sessionResult = await read(base);
  const proof = (await read(`${base}/identity`)).identity;
  const session = sessionResult.session;
  const expiry = Date.parse(proof?.sessionExpiresAt);
  if (proof?.sessionId !== sessionId || !['viewer','creator'].includes(proof.role) || typeof proof.actorId !== 'string' || !proof.actorId || (proof.role === 'viewer' && proof.viewerId !== proof.actorId) || (proof.role === 'creator' && proof.viewerId !== null) || session?.id !== sessionId || !Number.isFinite(expiry) || expiry <= Date.now() || signal?.aborted) throw new Error('unavailable');
  return {sessionId, role:proof.role, actorId:proof.actorId, expiresAt:proof.sessionExpiresAt, session};
}
