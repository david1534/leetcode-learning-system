# Pair Sum Indices

## Approach

### Initial reasoning

- Approach: Traverse nums once, using a hashmap from each seen value to its index and checking whether the current value's complement is already present.
- Why it fit: Hashmap lookup and insertion are O(1) average time, avoiding a nested traversal and allowing the array to be processed once.
- Invariant or key belief: Before processing index i, the hashmap maps values seen at earlier indices to their corresponding earlier indices.
- Expected complexity: O(n) average time and O(n) space.
- Edge case: For target 10 and nums [5, 5], check for the complement before storing the current value so the two distinct indices are returned.
- Recall quality: complete

### Final approach

Traverse the list once while storing each previously seen value and its index in a hashmap. For each current value, compute target minus that value and return the stored earlier index with the current index when the complement is present.

## Key invariant or insight

Before processing index i, the hashmap maps values from earlier indices to corresponding earlier indices. Checking for the complement before storing the current value guarantees distinct indices and correctly handles repeated values such as [5, 5].

## Complexity

- Time: `O(n) average time because each value is processed once and hashmap operations are O(1) on average.`
- Space: `O(n) space for the hashmap in the worst case.`

## Mistakes and lessons

Distinguish a loop invariant from a complexity justification. Check the complement before insertion to avoid reusing the current index; returning immediately when the pair is found would also make the implementation clearer.

## Assistance received

- Formal hints invoked: 0
- Highest assistance level: minor
- Minor (conversation): Clarified that processing each item once justifies complexity but does not state the loop invariant; the learner independently identified the hashmap-complement algorithm.

Minor conversational help clarified that processing every item once explains complexity but is not itself the invariant. The hashmap-complement algorithm, complexity, duplicate-value edge case, and implementation were independently reconstructed.

## Rating rationale

- Enforced maximum rating: Good
- Evidence: It passed with only minor clarification; multiple checkpoints or extra time were used.

Good is appropriate: the approach was independently recalled, all 4 cases passed on the first checkpoint, and only minor wording help was needed for the invariant. Eighteen minutes reflects the actual problem work and excludes the separate workflow-maintenance work.
