/** Only forward an internal reference, never a full account number. */
export function bankReference(value) {
  const reference = value.trim();
  return /^(?:demo|ref):[a-zA-Z0-9:_-]{1,100}$/.test(reference) ? reference : "";
}
