// The accepted private pointer is the publication commit record. Its archive
// references remain internal; only the explicit public fields leave the Worker.
export async function readElectricityPointer(kv, dataset, scope = '') {
  const options = { type: 'json', cacheTtl: 60 };
  return await kv.get(`private/${scope}${dataset}/current`, options)
    ?? await kv.get(`public/${scope}${dataset}/current`, options);
}

export function publicElectricityPointer(pointer) {
  const fields = ['schema', 'ok', 'lastSuccess', 'successfulDate', 'lastAttempt'];
  const recordFields = ['version', 'key', 'time', 'collectedAt'];
  const select = (value, keys) => Object.fromEntries(keys.filter(key => value[key] !== undefined).map(key => [key, value[key]]));
  return { ...select(pointer, fields), records: pointer.records.map(record => select(record, recordFields)) };
}
