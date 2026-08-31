# Longest Consecutive Streak

## Approach

### Initial reasoning

- Approach: Use a dynamically sized sliding window whose size depends on the maximum consecutive run length, moving it when a longer champion is found.
- Why it fit: It should traverse the list once instead of using nested loops to identify every consecutive candidate.
- Invariant or key belief: The left pointer moves only when a new champion is found.
- Expected complexity: O(n) time and O(n) space.
- Edge case: Unsure.
- Recall quality: novel

### Final approach

Convert the input to a set. A value begins a streak when value - 1 is absent. Starting from each such value, follow successive values through set membership, count that streak independently, and update the largest completed streak.

## Key invariant or insight

Index adjacency is irrelevant: the invariant is that an inner scan starts only at the smallest value of a streak. currStreak measures only that run, while largestStreak stores the best completed run.

## Complexity

- Time: `O(n) average time because set membership is O(1) average and expansion occurs only from sequence starts, so each distinct value is traversed once overall.`
- Space: `O(n) for the set of distinct input values.`

## Mistakes and lessons

I initially interpreted consecutive values as adjacent list positions and chose a sliding window. During implementation I treated values as list indices, checked an empty set against None, and accumulated separate streak lengths into one global counter. I learned to distinguish numeric relationships from container positions, and to separate current-candidate state from global-best state.

## Assistance received

- Formal hints invoked: 0
- Highest assistance level: guided
- Guided (conversation): Explained that sliding windows model adjacent indices and therefore do not represent consecutive values scattered through an unsorted list; prompted sequence-start recognition.
- Guided (conversation): Clarified that sorting the deduplicated values could produce the correct streak but costs O(n log n), then redirected toward identifying sequence starts through set membership.
- Minor (conversation): Confirmed forward set lookups with a streak counter and clarified that Python uses += 1 rather than ++.
- Guided (conversation): Clarified that O(1) set lookup alone does not make nested loops linear; total expansion is O(n) because only sequence starts expand and each distinct value is traversed by inner loops at most once overall.
- Minor (conversation): Clarified that Python sets are unordered and do not support indexing or slicing; values can be checked with membership or visited by iteration.
- Guided (conversation): Identified that listSet[num:] incorrectly treats a numeric value as a list index and that a list converted from a set has no consecutive-value ordering; redirected toward direct successor membership checks in the set.
- Guided (conversation): Clarified that sets have no meaningful indices and that streak traversal must follow numeric successor values rather than storage positions.
- Minor (conversation): Clarified that set(nums) always returns a set object, so an empty result is set() rather than None; emptiness must be tested as an empty collection.
- Guided (conversation): After 4/4 deterministic cases passed, identified that incrementing largestStreak inside every run accumulates separate streak lengths instead of tracking a per-run length and taking the maximum.

Guided questions redirected the approach from sliding windows and sorting to sequence-start recognition with a set, refined the O(n) argument, corrected value-versus-index traversal, and identified the separate-streak counter bug. Minor help covered Python set behavior, += 1, and empty-collection checks.

## Rating rationale

- Enforced maximum rating: Hard
- Evidence: It passed with guided algorithmic help or targeted debugging.

Hard is appropriate because the final solution is correct and passes all deterministic cases, but the core pattern and several correctness repairs required guided assistance. Passing tests and using no formal hints do not demonstrate independent recall.
