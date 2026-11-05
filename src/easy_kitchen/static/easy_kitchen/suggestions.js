const MAX_SUGGESTIONS = 20;

// Search all candidates when necessary, but stop once the visible list is full.
export function findSuggestions(candidates, matches) {
  const results = [];
  for (const candidate of candidates) {
    if (!matches(candidate)) continue;
    results.push(candidate);
    if (results.length === MAX_SUGGESTIONS) break;
  }
  return results;
}
